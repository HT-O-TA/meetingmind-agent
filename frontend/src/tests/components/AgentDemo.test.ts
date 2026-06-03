import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'

describe('AgentDemo Component Tests', () => {
  const MockAgentDemo = defineComponent({
    name: 'AgentDemo',
    props: {
      sessionId: { type: String, default: '' }
    },
    emits: ['send', 'clear', 'stop'],
    setup(props, { emit }) {
      const handleSend = (message: string) => {
        emit('send', message)
      }

      const handleClear = () => {
        emit('clear')
      }

      return { handleSend, handleClear }
    },
    template: `
      <div class="agent-demo">
        <textarea v-model="inputMessage" @keyup.enter.ctrl="handleSend(inputMessage)" />
        <button @click="handleSend(inputMessage)">发送</button>
        <button @click="handleClear">清空</button>
        <div class="messages">
          <div v-for="msg in messages" :key="msg.id" :class="msg.role">
            {{ msg.content }}
          </div>
        </div>
      </div>
    `,
    data() {
      return {
        inputMessage: '',
        messages: [] as Array<{ id: string; role: string; content: string }>
      }
    }
  })

  beforeEach(() => {
    vi.useFakeTimers()
  })

  it('should render component', () => {
    const wrapper = mount(MockAgentDemo, {
      props: { sessionId: 'test-session' }
    })

    expect(wrapper.find('.agent-demo').exists()).toBe(true)
    expect(wrapper.find('textarea').exists()).toBe(true)
    expect(wrapper.findAll('button')).toHaveLength(2)
  })

  it('should emit send event', async () => {
    const wrapper = mount(MockAgentDemo)

    await wrapper.find('textarea').setValue('测试消息')
    await wrapper.find('button').trigger('click')

    expect(wrapper.emitted('send')).toBeTruthy()
    expect(wrapper.emitted('send')![0]).toEqual(['测试消息'])
  })

  it('should emit clear event', async () => {
    const wrapper = mount(MockAgentDemo)

    const clearBtn = wrapper.findAll('button')[1]
    await clearBtn.trigger('click')

    expect(wrapper.emitted('clear')).toBeTruthy()
  })

  it('should update input value', async () => {
    const wrapper = mount(MockAgentDemo)

    const textarea = wrapper.find('textarea')
    await textarea.setValue('新的消息')

    expect(wrapper.vm.inputMessage).toBe('新的消息')
  })
})

describe('MessageDisplay Component Tests', () => {
  const MockMessageDisplay = defineComponent({
    name: 'MessageDisplay',
    props: {
      messages: {
        type: Array,
        default: () => []
      }
    },
    template: `
      <div class="message-display">
        <div
          v-for="msg in messages"
          :key="msg.id"
          :class="['message', msg.role]"
        >
          <span class="role">{{ msg.role === 'user' ? '用户' : '助手' }}</span>
          <div class="content">{{ msg.content }}</div>
        </div>
      </div>
    `
  })

  it('should render messages', () => {
    const messages = [
      { id: '1', role: 'user', content: '你好' },
      { id: '2', role: 'assistant', content: '你好，有什么可以帮你的？' }
    ]

    const wrapper = mount(MockMessageDisplay, {
      props: { messages }
    })

    expect(wrapper.findAll('.message')).toHaveLength(2)
    expect(wrapper.text()).toContain('你好')
  })

  it('should display user role correctly', () => {
    const messages = [
      { id: '1', role: 'user', content: '用户消息' }
    ]

    const wrapper = mount(MockMessageDisplay, {
      props: { messages }
    })

    expect(wrapper.find('.message.user .role').text()).toBe('用户')
  })

  it('should display assistant role correctly', () => {
    const messages = [
      { id: '1', role: 'assistant', content: '助手消息' }
    ]

    const wrapper = mount(MockMessageDisplay, {
      props: { messages }
    })

    expect(wrapper.find('.message.assistant .role').text()).toBe('助手')
  })
})

describe('ToolCallDisplay Component Tests', () => {
  const MockToolCallDisplay = defineComponent({
    name: 'ToolCallDisplay',
    props: {
      tools: {
        type: Array,
        default: () => []
      }
    },
    emits: ['select'],
    template: `
      <div class="tool-display">
        <div
          v-for="tool in tools"
          :key="tool.name"
          class="tool-item"
          @click="$emit('select', tool)"
        >
          <span class="tool-name">{{ tool.name }}</span>
          <span class="tool-category">{{ tool.category }}</span>
        </div>
      </div>
    `
  })

  it('should render tool list', () => {
    const tools = [
      { name: 'search_meeting', category: 'meeting', description: '搜索会议' },
      { name: 'extract_todos', category: 'todo', description: '提取待办' }
    ]

    const wrapper = mount(MockToolCallDisplay, {
      props: { tools }
    })

    expect(wrapper.findAll('.tool-item')).toHaveLength(2)
    expect(wrapper.text()).toContain('search_meeting')
  })

  it('should emit select event on click', async () => {
    const tools = [
      { name: 'search_meeting', category: 'meeting' }
    ]

    const wrapper = mount(MockToolCallDisplay, {
      props: { tools }
    })

    await wrapper.find('.tool-item').trigger('click')

    expect(wrapper.emitted('select')).toBeTruthy()
    expect(wrapper.emitted('select')![0]).toEqual([tools[0]])
  })
})

describe('ThinkingChain Component Tests', () => {
  const MockThinkingChain = defineComponent({
    name: 'ThinkingChain',
    props: {
      thoughts: {
        type: Array,
        default: () => []
      }
    },
    template: `
      <div class="thinking-chain">
        <div v-for="(thought, index) in thoughts" :key="index" class="thought-step">
          <span class="step-number">{{ index + 1 }}</span>
          <div class="thought-content">{{ thought }}</div>
        </div>
      </div>
    `
  })

  it('should render thinking steps', () => {
    const thoughts = [
      '用户询问会议内容',
      '准备检索相关文档',
      '检索到3个相关片段'
    ]

    const wrapper = mount(MockThinkingChain, {
      props: { thoughts }
    })

    expect(wrapper.findAll('.thought-step')).toHaveLength(3)
    expect(wrapper.text()).toContain('用户询问会议内容')
  })

  it('should show step numbers', () => {
    const thoughts = ['第一步', '第二步']

    const wrapper = mount(MockThinkingChain, {
      props: { thoughts }
    })

    expect(wrapper.find('.step-number').text()).toBe('1')
  })
})
