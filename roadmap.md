# Roadmap

> Generated with `docket docs roadmap`.

```mermaid
graph TD
  subgraph BUG
    BUG_1("BUG-1<br/>Fix Character Encoding<br/>Issue in FEAT-5<br/>p1 done")
    BUG_2("BUG-2<br/>Cannot Clear with Set<br/>Command<br/>p0 done")
    BUG_3("BUG-3<br/>Migrate Server to MCP<br/>2.x MCPServer API<br/>p0 done")
    BUG_4("BUG-4<br/>Add to Requires in CLI<br/>p1 done")
    BUG_5("BUG-5<br/>Serialize Ticket Writes<br/>Across Processes<br/>p3 done")
    BUG_6["BUG-6<br/>Key Removal Checks Usage<br/>Outside the Lock<br/>p4 todo"]
  end
  subgraph FEAT
    FEAT_1("FEAT-1<br/>Record Demo GIF with VHS<br/>p2 done")
    FEAT_2("FEAT-2<br/>Set Up and Publish to<br/>PyPI<br/>p3 done")
    FEAT_3("FEAT-3<br/>All Tickets Graph<br/>p2 done")
    FEAT_4("FEAT-4<br/>Shorthand for CLI<br/>p2 done")
    FEAT_5("FEAT-5<br/>Selection Options in CLI<br/>p2 done")
    FEAT_6["FEAT-6<br/>Templates for Tickets<br/>per Key<br/>p3 todo"]
    FEAT_7("FEAT-7<br/>Unified Version Code<br/>p1 done")
    FEAT_8["FEAT-8<br/>Host Flag<br/>p4 todo"]
    FEAT_9("FEAT-9<br/>Track Arbitrary<br/>Additional Metadata on<br/>Tickets/Groups<br/>p1 done")
    FEAT_10("FEAT-10<br/>Tree Style CLI Commands<br/>p2 done")
    FEAT_11("FEAT-11<br/>Repository Automation<br/>and Contribution<br/>Scaffolding<br/>p3 done")
    FEAT_12["FEAT-12<br/>Per Key Ticket Board<br/>View<br/>p2 todo"]
    FEAT_13("FEAT-13<br/>Check if Ticket Is Ready<br/>for Work<br/>p1 done")
    FEAT_14["FEAT-14<br/>Roadmap Graph Generation<br/>p2 todo"]
    FEAT_15("FEAT-15<br/>Use Title Case for<br/>Tickets<br/>p1 done")
    FEAT_16["FEAT-16<br/>Ticket Show Uses<br/>Optional Formatting<br/>p2 todo"]
    FEAT_17("FEAT-17<br/>Add Status to Graph<br/>Scope<br/>p1 done")
    FEAT_18("FEAT-18<br/>Offsite Ticket Authoring<br/>Brief<br/>p1 done")
    FEAT_19["FEAT-19<br/>Add Google Style<br/>Documentation Comments<br/>p1 todo"]
  end
  BUG_1 --> FEAT_2
  BUG_1 --> FEAT_5
  BUG_2 --> FEAT_2
  BUG_3 --> FEAT_2
  BUG_4 --> FEAT_2
  BUG_5 --> BUG_6
  BUG_5 --> FEAT_2
  FEAT_1 --> FEAT_2
  FEAT_2 --> FEAT_11
  FEAT_4 --> FEAT_2
  FEAT_5 --> FEAT_2
  FEAT_6 --> FEAT_12
  FEAT_7 --> FEAT_2
  FEAT_10 --> FEAT_2
  classDef doneP0 fill:#2d6a4f,color:#fff,stroke:#ff6b6b,stroke-width:4px
  classDef doneP1 fill:#2d6a4f,color:#fff,stroke:#ff922b,stroke-width:3px
  classDef doneP2 fill:#2d6a4f,color:#fff,stroke:#ffd43b,stroke-width:2px
  classDef doneP3 fill:#2d6a4f,color:#fff,stroke:#adb5bd,stroke-width:2px
  classDef todoP1 fill:#495057,color:#fff,stroke:#ff922b,stroke-width:3px
  classDef todoP2 fill:#495057,color:#fff,stroke:#ffd43b,stroke-width:2px
  classDef todoP3 fill:#495057,color:#fff,stroke:#adb5bd,stroke-width:2px
  classDef todoP4 fill:#495057,color:#fff,stroke:#6c757d,stroke-width:1px
  class BUG_2,BUG_3 doneP0
  class BUG_1,BUG_4,FEAT_13,FEAT_15,FEAT_17,FEAT_18,FEAT_7,FEAT_9 doneP1
  class FEAT_1,FEAT_10,FEAT_3,FEAT_4,FEAT_5 doneP2
  class BUG_5,FEAT_11,FEAT_2 doneP3
  class FEAT_19 todoP1
  class FEAT_12,FEAT_14,FEAT_16 todoP2
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
