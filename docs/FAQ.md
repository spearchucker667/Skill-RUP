# FAQ

**Q: Does the runtime execute destructive actions?**
A: Yes, if the agent is instructed to. The runtime operates on the codebase. It is strictly recommended to run Skill-RUP within a sandboxed/containerized environment, and always use Git for rollback capabilities.

**Q: Do I need to clone the upstream `RUP-Protocol` repository?**
A: No, all necessary protocol files are synchronized and bundled into the `protocol/` directory of this skill.

**Q: Does Skill-RUP support offline mode?**
A: Yes, the runtime and validation tools work entirely offline. However, your agent platform must be able to communicate with its respective LLM endpoint.
