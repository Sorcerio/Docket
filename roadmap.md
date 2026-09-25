# Roadmap: todo

> Generated with `docket docs roadmap`.

```mermaid
graph TD
  subgraph BUG
    BUG_6["BUG-6<br/>Key Removal Checks Usage<br/>Outside the Lock<br/>p4 todo"]
  end
  subgraph FEAT
    FEAT_6["FEAT-6<br/>Templates for Tickets<br/>per Key<br/>p3 todo"]
    FEAT_8["FEAT-8<br/>Host Flag<br/>p4 todo"]
    FEAT_12["FEAT-12<br/>Per Key Ticket Board<br/>View<br/>p2 todo"]
    FEAT_16["FEAT-16<br/>Ticket Show Uses<br/>Optional Formatting<br/>p2 todo"]
    FEAT_19["FEAT-19<br/>Add Google Style<br/>Documentation Comments<br/>p1 todo"]
    FEAT_20["FEAT-20<br/>CLI Accessors for All<br/>Headmatter<br/>p0 todo"]
  end
  FEAT_6 --> FEAT_12
  classDef todoP0 fill:#495057,color:#fff,stroke:#ff6b6b,stroke-width:4px
  classDef todoP1 fill:#495057,color:#fff,stroke:#ff922b,stroke-width:3px
  classDef todoP2 fill:#495057,color:#fff,stroke:#ffd43b,stroke-width:2px
  classDef todoP3 fill:#495057,color:#fff,stroke:#adb5bd,stroke-width:2px
  classDef todoP4 fill:#495057,color:#fff,stroke:#6c757d,stroke-width:1px
  class FEAT_20 todoP0
  class FEAT_19 todoP1
  class FEAT_12,FEAT_16 todoP2
  class FEAT_6 todoP3
  class BUG_6,FEAT_8 todoP4
```

## Legend

| Shape | Status |
|---|---|
| `[ ]` | todo, not started |
| `{ }` | wip, in flight |
| `( )` | done |

Arrows indicate required order of operations.

Each node's border represents its priority. Heaviest is higher priority.
