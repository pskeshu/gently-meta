"""
gently-meta API Server

RESTful API for multi-microscope coordination.
Handles experiment submission, review, microscope registration, and status tracking.
"""

import os
from datetime import datetime
from typing import Any

from flask import Flask, jsonify, request
from flask_cors import CORS

from .queue import ExperimentQueue, RequestStatus, BiologicalQuery
from .microscope_registry import MicroscopeRegistry, MicroscopeCapability, MicroscopeType, MicroscopeStatus
from .notifications import NotificationService


def create_app(
    queue_path: str = None,
    registry_path: str = None,
    notification_config_path: str = None,
) -> Flask:
    """Create and configure the Flask application."""

    app = Flask(__name__)
    CORS(app)

    # Initialize services
    queue_path = queue_path or os.getenv("QUEUE_STORAGE_PATH", "gently_meta_queue.json")
    registry_path = registry_path or os.getenv("MICROSCOPE_REGISTRY_PATH", "gently_meta_microscopes.json")
    notification_config_path = notification_config_path or os.getenv("NOTIFICATION_CONFIG_PATH", "notification_config.json")

    queue = ExperimentQueue(storage_path=queue_path)
    registry = MicroscopeRegistry(storage_path=registry_path)
    notifications = NotificationService(config_path=notification_config_path)

    # ========================================================================
    # Health & Info Endpoints
    # ========================================================================

    @app.route('/api/v1/health', methods=['GET'])
    def health_check():
        """Health check endpoint."""
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "queue_size": len(queue.requests),
            "microscopes_online": len(registry.list(status="online")),
        }), 200

    @app.route('/api/v1/info', methods=['GET'])
    def api_info():
        """API information endpoint."""
        return jsonify({
            "name": "gently-meta",
            "version": "0.1.0",
            "description": "Multi-microscope coordination infrastructure",
            "endpoints": {
                "experiments": "/api/v1/experiments",
                "review": "/api/v1/review",
                "microscopes": "/api/v1/microscopes",
                "stats": "/api/v1/stats",
            },
        }), 200

    # ========================================================================
    # Experiment Endpoints
    # ========================================================================

    @app.route('/api/v1/experiments', methods=['POST'])
    def submit_experiment():
        """Submit a new experiment request."""
        try:
            data = request.json

            required_fields = ['sample_spec', 'requester', 'experiment']
            if not all(field in data for field in required_fields):
                return jsonify({
                    "error": "Missing required fields",
                    "required": required_fields,
                }), 400

            req = queue.submit(
                sample_spec=data['sample_spec'],
                requester_name=data['requester']['name'],
                requester_email=data['requester']['email'],
                requester_institution=data['requester']['institution'],
                microscope_system=data['experiment']['microscope_system'],
                scientific_rationale=data['experiment']['scientific_rationale'],
                priority=data['experiment'].get('priority', 'medium'),
                department=data['requester'].get('department'),
                country=data['requester'].get('country'),
                orcid=data['requester'].get('orcid'),
            )

            # Notify reviewers
            notifications.notify_new_submission(
                request_id=req.request_id,
                microscope_system=req.microscope_system,
                requester_name=req.requester.name,
                requester_institution=req.requester.institution,
                priority=req.priority.value,
                scientific_rationale=req.scientific_rationale,
            )

            return jsonify({
                "request_id": req.request_id,
                "status": req.status.value,
                "message": "Experiment request submitted successfully",
            }), 201

        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": "Internal server error", "details": str(e)}), 500

    @app.route('/api/v1/experiments/<request_id>', methods=['GET'])
    def get_experiment(request_id: str):
        """Get details of a specific experiment."""
        req = queue.get(request_id)
        if not req:
            return jsonify({"error": "Request not found"}), 404
        return jsonify(req.to_dict()), 200

    @app.route('/api/v1/experiments', methods=['GET'])
    def list_experiments():
        """List experiments with optional filtering."""
        try:
            filters = {
                'status': request.args.get('status'),
                'microscope_system': request.args.get('microscope'),
                'priority': request.args.get('priority'),
                'requester_email': request.args.get('requester'),
            }
            filters = {k: v for k, v in filters.items() if v is not None}

            results = queue.list(**filters)

            return jsonify({
                "count": len(results),
                "experiments": [req.to_dict() for req in results],
            }), 200

        except ValueError as e:
            return jsonify({"error": f"Invalid filter value: {e}"}), 400

    @app.route('/api/v1/experiments/<request_id>/status', methods=['PUT'])
    def update_experiment_status(request_id: str):
        """Update experiment execution status."""
        try:
            data = request.json
            if not data or 'status' not in data:
                return jsonify({"error": "status is required"}), 400

            success = queue.update_status(
                request_id=request_id,
                new_status=data['status'],
                actor=data.get('actor', 'system'),
                results_location=data.get('results_location'),
                notes=data.get('notes'),
            )

            if not success:
                return jsonify({"error": "Request not found"}), 404

            req = queue.get(request_id)

            # Notify on completion
            if data['status'] == 'completed':
                notifications.notify_completion(
                    requester_email=req.requester.email,
                    request_id=request_id,
                    results_location=data.get('results_location'),
                )

            return jsonify({
                "message": f"Status updated to {data['status']}",
                "request_id": request_id,
                "status": data['status'],
            }), 200

        except ValueError as e:
            return jsonify({"error": f"Invalid status value: {e}"}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ========================================================================
    # Review Endpoints
    # ========================================================================

    @app.route('/api/v1/review/pending', methods=['GET'])
    def get_pending_reviews():
        """Get experiments pending review."""
        microscope = request.args.get('microscope')
        pending = queue.get_pending_review(microscope_system=microscope)

        return jsonify({
            "count": len(pending),
            "pending_reviews": [req.to_dict() for req in pending],
        }), 200

    @app.route('/api/v1/review/<request_id>/approve', methods=['POST'])
    def approve_experiment(request_id: str):
        """Approve an experiment request."""
        try:
            data = request.json
            if not data or 'reviewer_name' not in data:
                return jsonify({"error": "reviewer_name is required"}), 400

            success = queue.approve(
                request_id=request_id,
                reviewer_name=data['reviewer_name'],
                reviewer_email=data.get('reviewer_email'),
                comments=data.get('comments', ''),
                scheduled_date=data.get('scheduled_date'),
                assigned_microscope_id=data.get('assigned_microscope_id'),
            )

            if not success:
                return jsonify({"error": "Request not found"}), 404

            req = queue.get(request_id)
            notifications.notify_approval(
                requester_email=req.requester.email,
                request_id=request_id,
                reviewer_name=data['reviewer_name'],
                comments=data.get('comments'),
                scheduled_date=data.get('scheduled_date'),
            )

            return jsonify({
                "message": "Experiment approved",
                "request_id": request_id,
                "status": req.status.value,
            }), 200

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/v1/review/<request_id>/reject', methods=['POST'])
    def reject_experiment(request_id: str):
        """Reject an experiment request."""
        try:
            data = request.json
            if not data or 'reviewer_name' not in data or 'comments' not in data:
                return jsonify({
                    "error": "reviewer_name and comments are required"
                }), 400

            success = queue.reject(
                request_id=request_id,
                reviewer_name=data['reviewer_name'],
                comments=data['comments'],
                reviewer_email=data.get('reviewer_email'),
            )

            if not success:
                return jsonify({"error": "Request not found"}), 404

            req = queue.get(request_id)
            notifications.notify_rejection(
                requester_email=req.requester.email,
                request_id=request_id,
                reviewer_name=data['reviewer_name'],
                comments=data['comments'],
            )

            return jsonify({
                "message": "Experiment rejected",
                "request_id": request_id,
                "status": "rejected",
            }), 200

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/v1/review/<request_id>/request-revision', methods=['POST'])
    def request_revision(request_id: str):
        """Request revisions to an experiment."""
        try:
            data = request.json
            if not data or 'reviewer_name' not in data or 'requested_modifications' not in data:
                return jsonify({
                    "error": "reviewer_name and requested_modifications are required"
                }), 400

            success = queue.request_revision(
                request_id=request_id,
                reviewer_name=data['reviewer_name'],
                requested_modifications=data['requested_modifications'],
                comments=data.get('comments', ''),
                reviewer_email=data.get('reviewer_email'),
            )

            if not success:
                return jsonify({"error": "Request not found"}), 404

            return jsonify({
                "message": "Revision requested",
                "request_id": request_id,
                "status": "revision_requested",
            }), 200

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/v1/queue/approved', methods=['GET'])
    def get_approved_queue():
        """Get approved experiments ready for execution."""
        microscope = request.args.get('microscope')
        approved = queue.get_approved_queue(microscope_system=microscope)

        return jsonify({
            "count": len(approved),
            "approved_experiments": [req.to_dict() for req in approved],
        }), 200

    # ========================================================================
    # Sample Search Endpoints
    # ========================================================================

    @app.route('/api/v1/samples/search', methods=['GET', 'POST'])
    def search_samples():
        """
        Search experiments by biological context.

        GET params or POST JSON body:
            cell_line: str - Cell line (partial match, e.g., "HeLa", "MCF")
            organism: str - Organism (partial match, e.g., "human", "mouse")
            tissue_type: str - Tissue type (partial match)
            genetic_modifications: list[str] - Match any modification
            fluorescent_proteins: list[str] - Match any FP (e.g., ["GFP", "mCherry"])
            antibody_targets: list[str] - Match any antibody target
            fluorophores: list[str] - Match any fluorophore
            nuclear_stain: str - Nuclear stain (partial match)
            compound_names: list[str] - Match any treatment compound
            microscope_type: str - Microscope type
            has_z_stack: bool - Filter for z-stack experiments
            has_time_lapse: bool - Filter for time-lapse experiments
            live_cell: bool - Filter for live vs fixed samples
            status: str - Request status filter

        Returns:
            List of matching experiments with sample summaries.

        Example queries:
            GET /api/v1/samples/search?cell_line=HeLa&has_time_lapse=true
            GET /api/v1/samples/search?fluorescent_proteins=GFP&fluorescent_proteins=mCherry
            POST /api/v1/samples/search {"organism": "human", "live_cell": true}
        """
        try:
            # Accept both GET params and POST body
            if request.method == 'POST' and request.json:
                params = request.json
            else:
                params = {}
                # String fields
                for field in ['cell_line', 'organism', 'tissue_type', 'nuclear_stain',
                              'microscope_type', 'status']:
                    if request.args.get(field):
                        params[field] = request.args.get(field)

                # List fields (can be specified multiple times)
                for field in ['genetic_modifications', 'fluorescent_proteins',
                              'antibody_targets', 'fluorophores', 'compound_names']:
                    values = request.args.getlist(field)
                    if values:
                        params[field] = values

                # Boolean fields
                for field in ['has_z_stack', 'has_time_lapse', 'live_cell']:
                    val = request.args.get(field)
                    if val is not None:
                        params[field] = val.lower() == 'true'

            # Build query and search
            bio_query = BiologicalQuery(**params)
            results = queue.find_by_biology(bio_query)

            # Return summaries for easier consumption
            summaries = [queue.get_sample_summary(req.request_id) for req in results]

            return jsonify({
                "count": len(results),
                "query": {k: v for k, v in params.items() if v is not None},
                "samples": summaries,
            }), 200

        except TypeError as e:
            return jsonify({"error": f"Invalid query parameter: {e}"}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/v1/samples/<request_id>/summary', methods=['GET'])
    def get_sample_summary(request_id: str):
        """Get biological context summary for a specific experiment."""
        summary = queue.get_sample_summary(request_id)
        if not summary:
            return jsonify({"error": "Request not found"}), 404
        return jsonify(summary), 200

    # ========================================================================
    # Microscope Registry Endpoints
    # ========================================================================

    @app.route('/api/v1/microscopes', methods=['GET'])
    def list_microscopes():
        """List registered microscopes."""
        filters = {
            'type': request.args.get('type'),
            'status': request.args.get('status'),
            'capability': request.args.get('capability'),
        }
        filters = {k: v for k, v in filters.items() if v is not None}

        microscopes = registry.list(**filters)

        return jsonify({
            "count": len(microscopes),
            "microscopes": [mic.to_dict() for mic in microscopes],
        }), 200

    @app.route('/api/v1/microscopes/<microscope_id>', methods=['GET'])
    def get_microscope(microscope_id: str):
        """Get details of a specific microscope."""
        mic = registry.get(microscope_id)
        if not mic:
            return jsonify({"error": "Microscope not found"}), 404
        return jsonify(mic.to_dict()), 200

    @app.route('/api/v1/microscopes/register', methods=['POST'])
    def register_microscope():
        """Register a new microscope."""
        try:
            data = request.json
            if not data or 'microscope_id' not in data or 'type' not in data:
                return jsonify({
                    "error": "microscope_id and type are required"
                }), 400

            mic = MicroscopeCapability.from_dict({
                **data,
                "status": data.get("status", "offline"),
            })

            registry.register(mic)

            return jsonify({
                "message": "Microscope registered",
                "microscope_id": mic.microscope_id,
            }), 201

        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/v1/microscopes/<microscope_id>/status', methods=['PUT'])
    def update_microscope_status(microscope_id: str):
        """Update microscope operational status."""
        try:
            data = request.json
            if not data or 'status' not in data:
                return jsonify({"error": "status is required"}), 400

            success = registry.update_status(microscope_id, data['status'])

            if not success:
                return jsonify({"error": "Microscope not found"}), 404

            return jsonify({
                "message": f"Status updated to {data['status']}",
                "microscope_id": microscope_id,
            }), 200

        except ValueError as e:
            return jsonify({"error": f"Invalid status: {e}"}), 400

    @app.route('/api/v1/microscopes/<microscope_id>/heartbeat', methods=['POST'])
    def microscope_heartbeat(microscope_id: str):
        """Record a heartbeat from a microscope."""
        success = registry.heartbeat(microscope_id)

        if not success:
            return jsonify({"error": "Microscope not found"}), 404

        return jsonify({
            "message": "Heartbeat recorded",
            "microscope_id": microscope_id,
            "timestamp": datetime.utcnow().isoformat(),
        }), 200

    @app.route('/api/v1/microscopes/find', methods=['GET'])
    def find_microscopes():
        """Find microscopes matching requirements."""
        microscope_type = request.args.get('type')
        capabilities = request.args.getlist('capability')
        wavelengths = [int(w) for w in request.args.getlist('wavelength')]
        magnification = request.args.get('magnification')
        only_available = request.args.get('available', 'true').lower() == 'true'

        matches = registry.find_suitable(
            microscope_type=microscope_type,
            required_capabilities=capabilities or None,
            required_wavelengths=wavelengths or None,
            required_magnification=int(magnification) if magnification else None,
            only_available=only_available,
        )

        return jsonify({
            "count": len(matches),
            "microscopes": [mic.to_dict() for mic in matches],
        }), 200

    # ========================================================================
    # Statistics Endpoints
    # ========================================================================

    @app.route('/api/v1/stats', methods=['GET'])
    def get_statistics():
        """Get queue and registry statistics."""
        queue_stats = queue.get_stats()

        microscope_stats = {
            "total": len(registry.microscopes),
            "online": len(registry.list(status="online")),
            "offline": len(registry.list(status="offline")),
            "busy": len(registry.list(status="busy")),
            "by_type": {},
        }

        for mic in registry.microscopes.values():
            type_key = mic.type.value
            microscope_stats["by_type"][type_key] = microscope_stats["by_type"].get(type_key, 0) + 1

        return jsonify({
            "timestamp": datetime.utcnow().isoformat(),
            "queue": queue_stats,
            "microscopes": microscope_stats,
        }), 200

    return app


# Create default app instance
app = create_app()


def main():
    """Run the API server."""
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'false').lower() == 'true'

    print(f"""
    ╔══════════════════════════════════════════════════════════════╗
    ║  gently-meta API Server                                       ║
    ║  Multi-Microscope Coordination Infrastructure                 ║
    ║                                                              ║
    ║  Running on http://0.0.0.0:{port:<5}                           ║
    ║                                                              ║
    ║  Endpoints:                                                  ║
    ║  - GET    /api/v1/health              Health check           ║
    ║  - POST   /api/v1/experiments         Submit experiment      ║
    ║  - GET    /api/v1/experiments         List experiments       ║
    ║  - GET    /api/v1/review/pending      Pending reviews        ║
    ║  - POST   /api/v1/review/:id/approve  Approve request        ║
    ║  - POST   /api/v1/review/:id/reject   Reject request         ║
    ║  - GET    /api/v1/microscopes         List microscopes       ║
    ║  - POST   /api/v1/microscopes/register Register microscope  ║
    ║  - GET    /api/v1/stats               Statistics             ║
    ╚══════════════════════════════════════════════════════════════╝
    """)

    app.run(host='0.0.0.0', port=port, debug=debug)


if __name__ == '__main__':
    main()
