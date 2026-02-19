# TODO

## Backlog

### Refactor LLM judge into router architecture
- Introduce `BaseJudge` ABC with `evaluate()` method
- Implement `JudgeRouter` that dispatches to specialized micro-judges per rule type
- Refactor existing `LLMJudge` into `CerebrasJudge` extending `BaseJudge`
- Add training data flywheel: collect (payload, rule, verdict) tuples from judge evaluations for future fine-tuning
