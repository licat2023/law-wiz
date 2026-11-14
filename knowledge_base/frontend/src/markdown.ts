/** 知识库文档的 Markdown 渲染和原文高亮切片。 */
import MarkdownIt from 'markdown-it'

const renderer = new MarkdownIt({ html: false, linkify: false, breaks: true })
renderer.disable('image')
renderer.validateLink = (url) => /^(https?:|mailto:|#|\/)/i.test(url) && !url.startsWith('//')
/** 禁用原始 HTML 和图片，并限制允许的链接地址，再生成展示用 HTML。 */
export const renderMarkdown = (source: string) => renderer.render(source)
/**
 * 将解析正文按 [start, end) 划为命中前、命中区和命中后三段。
 * 服务端偏移按 Unicode 码点计算，故先展开字符串再切片。
 */
export function sourceParts(text: string, start: number, end: number): [string, string, string] {
  const chars = Array.from(text)
  return [
    chars.slice(0, start).join(''),
    chars.slice(start, end).join(''),
    chars.slice(end).join(''),
  ]
}
