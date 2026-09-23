from app.agent.registry import AgentRegistry
from app.agent.runtime import AgentRuntime


def main():

    # 1. 创建 Agent 注册中心
    # Registry内部会自动注册：
    # demo -> DemoAgent()
    registry = AgentRegistry()


    # 2. 创建 Runtime
    # Runtime负责调度Agent
    runtime = AgentRuntime(
        registry
    )


    # 3. 调用Agent
    result = runtime.invoke(
        agent_code="demo",
        message="你好，这是一次Runtime测试",
        scene="CONNECTIVITY_TEST"
    )


    # 4. 查看结果
    print(result)

    agent = registry.get("demo")

    print(type(agent))
if __name__ == "__main__":
    main()