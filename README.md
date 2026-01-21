# gently-meta

Infrastructure for coordinating multiple [gently](https://github.com/pskeshu/gently) systems.

**Status**: Early concept.

## Vision

A single gently instance controls one microscope. But real facilities have multiple instruments, shared compute resources, sample handling robotics, and complex logistics. gently-meta is the coordination layer above individual gently instances.

## Scope

**Multi-microscope coordination**
- Route samples to the right instrument based on availability and capability
- Coordinate handoffs between imaging modalities
- Share calibration and perception models across instruments

**Shared resources**
- HPC job scheduling for compute-intensive analysis
- Liquid handling and sample preparation robotics
- Storage and data management across instruments

**Facility-level intelligence**
- Sample tracking across instruments
- Experiment scheduling and prioritization
- Resource allocation and load balancing

## Relationship to [gently](https://github.com/pskeshu/gently)

```
┌─────────────────────────────────────────────┐
│              gently-meta                     │
│    (facility coordination layer)             │
└─────────────┬───────────────┬───────────────┘
              │               │
      ┌───────▼───────┐ ┌─────▼───────┐
      │   gently      │ │   gently    │  ...
      │  (diSPIM)     │ │ (confocal)  │
      └───────────────┘ └─────────────┘
```

Each gently instance remains autonomous. gently-meta provides coordination without replacing local control.

## Open Questions

- Protocol for gently instances to advertise capabilities?
- How to handle heterogeneous microscope types?
- Sample identity across instruments?
- Failure handling when one instrument goes down?

## Contributing

This is early-stage thinking. Ideas welcome.

## License

See [LICENSE](LICENSE) file.
