# gently-meta: Global Registry for Microscopy Resources

Infrastructure for coordinating multiple [gently](https://github.com/pskeshu/gently) systems.

**gently-meta** is a registry and discovery service for autonomous microscopy systems. It acts as a global resource that individual gently instances (autonomous microscopes) can query to discover other resources, coordinate experiments, and share compute infrastructure.

## The Big Picture

The Human Genome Project succeeded by coordinating sequencing across multiple centers worldwide - standardized formats, shared repositories, capability discovery. No single lab could have done it alone.

**Microscopy is where sequencing was 25 years ago.** Experiments are facility-specific, hard to reproduce, limited by single-instrument thinking. gently-meta aims to change that.

Imagine:
- A researcher in Tokyo submits an experiment requiring fast volumetric imaging
- gently-meta routes it to an available DiSPIM in Boston
- Results flow to shared storage, processed by HPC in Frankfurt
- A VLM monitors quality in real-time
- The Model project generates the next hypothesis
- Another facility picks up the follow-up experiment

**Global coordination of imaging experiments.**

## Vision

A single [gently](https://github.com/pskeshu/gently) instance controls one microscope. But real facilities have multiple instruments, shared compute resources, sample handling robotics, and complex logistics. gently-meta is the coordination layer above individual gently instances.

Modern microscopy facilities have multiple instruments, compute resources, and analysis capabilities distributed across locations. gently-meta provides:

1. **Resource Registry**: Discover microscopes, HPC clusters, and VLMs available across the facility
2. **Experiment Queue**: Researchers submit requests; reviewers approve and route to appropriate resources
3. **Sample Specifications**: Standardized schemas ensure reproducibility across instruments
4. **Capability Matching**: Match experiment requirements to available resources

Individual gently instances remain **autonomous** - gently-meta is a registry they query, not a command layer.

## Architecture

```
                    ┌─────────────┐
                    │    Model    │  (hypothesis generation)
                    │  (future)   │
                    └──────┬──────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                        gently-meta                               │
│                (global resource registry)                        │
│                                                                  │
│  • Microscope registry      • Experiment queue                   │
│  • Compute resources        • Sample specifications              │
│  • Capability discovery     • Workflow coordination              │
└───┬─────────────┬─────────────┬─────────────┬───────────────────┘
    │             │             │             │
    ▼             ▼             ▼             ▼
┌────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│ gently │  │  gently  │  │   HPC    │  │   VLM    │
│(diSPIM)│  │(widefield)│  │ (deconv, │  │  (QC,    │
└───┬────┘  └────┬─────┘  │ segment) │  │ monitor) │
    │            │        └──────────┘  └──────────┘
    │            │              ▲             ▲
    └────────────┴──────────────┴─────────────┘
                        │
                   data store
```

### How it works

1. **gently instances register** their capabilities with gently-meta on startup
2. **Compute resources** (HPC, VLM) also register as available services
3. **Researchers submit experiments** to gently-meta's queue
4. **Reviewers approve** and gently-meta matches requests to capable resources
5. **gently instances query** gently-meta to discover:
   - Other microscopes (for multi-modal experiments)
   - HPC resources (for heavy processing)
   - VLM services (for real-time QC)
6. **Results flow** to shared data store, accessible to all registered resources

## Scope

### Multi-microscope coordination
- Route samples to the right instrument based on availability and capability
- Coordinate handoffs between imaging modalities
- Share calibration and perception models across instruments

### Shared resources
- HPC job scheduling for compute-intensive analysis
- Liquid handling and sample preparation robotics
- Storage and data management across instruments

### Facility-level intelligence
- Sample tracking across instruments
- Experiment scheduling and prioritization
- Resource allocation and load balancing

## Components

### Resource Types

gently-meta can register and track different resource types:

| Type | Description | Examples |
|------|-------------|----------|
| `microscope` | Imaging instruments | DiSPIM, confocal, widefield |
| `compute` | Processing clusters | Slurm HPC, GPU nodes |
| `vlm` | Vision-language models | Local LLaVA, Ollama instance |
| `storage` | Data repositories | NAS, object storage |
| `analysis` | Analysis services | Segmentation, tracking |
| `robotics` | Sample handling | Liquid handlers, plate movers |

### Phase 1: Infrastructure (Current)

- **Resource Registry** (`gently_meta/microscope_registry.py`): Register and discover any resource type
- **Experiment Queue** (`gently_meta/queue.py`): Priority-based queue with approval workflow
- **Sample Specification** (`schemas/sample_spec.json`): Complete experimental context schema
- **Coordination API** (`gently_meta/api.py`): REST endpoints for resource discovery and experiment management
- **Notification Service** (`gently_meta/notifications.py`): Email-based workflow coordination

### Phase 2: Intelligence (Future)

- Active learning loop integration (Model project)
- Hypothesis generation from experimental results
- Automated experiment routing based on scientific goals
- Multi-resource experiment orchestration

## Key Concepts

### Sample Specification (Sample_Spec)

The Sample_Spec defines the complete experimental context required to produce reproducible biological observations. It serves as:

- **Model Input**: Describes conditions that produced experimental data
- **Model Output**: Specifies conditions for the next experiment
- **Communication Protocol**: Standardized format between researchers, coordinators, and instruments

See `schemas/sample_spec.json` for the complete schema.

### Biological Context Search

Search experiments by biological properties to find samples of a specific kind:

```bash
# Find all HeLa cell experiments
curl "/api/v1/samples/search?cell_line=HeLa"

# Find live-cell time-lapse experiments
curl "/api/v1/samples/search?live_cell=true&has_time_lapse=true"

# Find experiments with GFP or mCherry markers
curl "/api/v1/samples/search?fluorescent_proteins=GFP&fluorescent_proteins=mCherry"

# Complex query via POST
curl -X POST /api/v1/samples/search -H "Content-Type: application/json" -d '{
  "organism": "human",
  "antibody_targets": ["tubulin", "actin"],
  "microscope_type": "confocal"
}'
```

**Searchable fields:**

| Category | Fields |
|----------|--------|
| Biology | `cell_line`, `organism`, `tissue_type` |
| Genetic | `genetic_modifications`, `fluorescent_proteins` |
| Staining | `antibody_targets`, `fluorophores`, `nuclear_stain` |
| Treatment | `compound_names` |
| Imaging | `microscope_type`, `has_z_stack`, `has_time_lapse`, `live_cell` |
| Workflow | `status` |

String fields use partial case-insensitive matching. List fields match if any item overlaps.

**Python API:**

```python
from gently_meta.queue import ExperimentQueue, BiologicalQuery

queue = ExperimentQueue()

# Search with kwargs
results = queue.find_by_biology(cell_line="HeLa", has_time_lapse=True)

# Search with query object
query = BiologicalQuery(
    organism="human",
    fluorescent_proteins=["GFP"],
    live_cell=True
)
results = queue.find_by_biology(query)

# Get summary for a specific sample
summary = queue.get_sample_summary(request_id)
```

### Experiment Request Lifecycle

```
SUBMITTED ────► UNDER_REVIEW ────► APPROVED ────► SCHEDULED ────► IN_PROGRESS ────► COMPLETED
                     │
                     └────────────► REJECTED
                     │
                     └────────────► REVISION_REQUESTED
```

### Microscope Capability Advertisement

Each gently instance advertises its capabilities:

```json
{
  "microscope_id": "dispim-001",
  "type": "light_sheet",
  "capabilities": ["3d_imaging", "live_cell", "fast_acquisition"],
  "channels": [405, 488, 561, 640],
  "objectives": [10, 20, 40, 63],
  "special_modes": ["TIRF", "FRAP"]
}
```

gently-meta matches experiment requirements to available instruments.

## Quick Start

### Installation

```bash
pip install -e .
```

### Run the API Server

```bash
python -m gently_meta.api
```

### Submit an Experiment

```python
import requests

response = requests.post('http://localhost:5000/api/v1/experiments', json={
    "sample_spec": {
        "sample_id": "hela_timelapse_001",
        "biological_context": {
            "cell_line": "HeLa",
            "passage_number": 12
        },
        "imaging_parameters": {
            "microscope_type": "widefield",
            "channels": [{"name": "DAPI", "excitation": 405}],
            "time_lapse": {"enabled": True, "interval": 300}
        }
    },
    "requester": {
        "name": "Dr. Jane Smith",
        "email": "jsmith@university.edu",
        "institution": "University of Biology"
    },
    "experiment": {
        "microscope_system": "DiSPIM",
        "scientific_rationale": "Study cell division dynamics...",
        "priority": "high"
    }
})

print(f"Request ID: {response.json()['request_id']}")
```

## API Endpoints

### Experiment Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/experiments` | Submit new experiment |
| GET | `/api/v1/experiments` | List experiments (with filters) |
| GET | `/api/v1/experiments/{id}` | Get experiment details |
| PUT | `/api/v1/experiments/{id}/status` | Update experiment status |

### Review Workflow

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/review/pending` | Get pending reviews |
| POST | `/api/v1/review/{id}/approve` | Approve experiment |
| POST | `/api/v1/review/{id}/reject` | Reject experiment |

### Resource Registry

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/microscopes` | List available resources |
| POST | `/api/v1/microscopes/register` | Register new resource |
| PUT | `/api/v1/microscopes/{id}/status` | Update resource status |
| GET | `/api/v1/microscopes/find` | Find resources by capability |

### Sample Search

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/api/v1/samples/search` | Search by biological context |
| GET | `/api/v1/samples/{id}/summary` | Get sample summary |

### Statistics

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/stats` | Queue statistics |
| GET | `/api/v1/health` | Health check |

## Configuration

### Environment Variables

```bash
export QUEUE_STORAGE_PATH=/path/to/queue.json
export MICROSCOPE_REGISTRY_PATH=/path/to/microscopes.json
export SMTP_SERVER=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USER=your_email@gmail.com
export SMTP_PASSWORD=your_app_password
export FROM_EMAIL=experiments@lab.org
export PORT=5000
```

### Notification Configuration

Edit `notification_config.json` to configure reviewers for each microscope system:

```json
{
  "enabled": true,
  "reviewers": {
    "DiSPIM": ["ryan@lab.org"],
    "confocal": ["imaging-team@lab.org"]
  }
}
```

## Relationship to Other Components

### [gently](https://github.com/pskeshu/gently) Instances

Each gently instance is autonomous but benefits from the registry:
- **Registers** its capabilities on startup
- **Queries** for compute resources when needed
- **Discovers** other microscopes for multi-modal workflows
- **Reports** status and results back to gently-meta

### Model Project (Intelligence Layer)

gently-meta provides the **registry and coordination layer**; Model provides the **intelligence**:

| gently-meta (Registry) | Model (Intelligence) |
|------------------------|---------------------|
| Resource discovery | Active learning loop |
| Experiment queue | Hypothesis generation |
| Capability matching | Experiment design |
| Sample specifications | Representation updating |

Model queries gently-meta to find resources, then directs experiments based on scientific goals.

### Compute Resources

| Resource | Role | Example Uses |
|----------|------|--------------|
| **HPC** | Heavy batch processing | Deconvolution, segmentation, large-scale analysis |
| **VLM** | Real-time understanding | QC monitoring, anomaly detection, experiment guidance |

Compute resources register with gently-meta just like microscopes. A gently instance can query:
```python
# Find available deconvolution service
hpc = gently_meta.find(capability="deconvolution", status="online")

# Find VLM for quality control
vlm = gently_meta.find(type="vlm", capability="image_qc")
```

## Development

### Project Structure

```
gently-meta/
├── README.md
├── LICENSE
├── pyproject.toml
├── schemas/
│   ├── sample_spec.json          # Sample specification JSON schema
│   ├── experiment_request.json   # Experiment request schema
│   └── microscope_capability.json # Microscope capability schema
├── gently_meta/
│   ├── __init__.py
│   ├── queue.py                  # Experiment queue management
│   ├── api.py                    # REST API server
│   ├── notifications.py          # Notification service
│   └── microscope_registry.py    # Resource registry
└── tests/
    └── test_queue.py
```

### Running Tests

```bash
pytest tests/
```

## Open Questions

- Federation across institutions?
- Authentication and authorization model?
- Data sovereignty and privacy constraints?
- Handling network partitions and offline operation?

## Contributing

Ideas and contributions welcome. See issues for current discussions.

## License

See [LICENSE](LICENSE) file.
