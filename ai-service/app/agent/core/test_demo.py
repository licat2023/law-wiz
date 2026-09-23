from demo_agent import DemoAgent

if __name__ == '__main__':
    agent = DemoAgent()
    result = agent.invoke(message="你好Agent", scene="chat")
    print(result)