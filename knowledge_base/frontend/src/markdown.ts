import MarkdownIt from 'markdown-it'

const renderer = new MarkdownIt({ html: false, linkify: false, breaks: true })
renderer.disable('image')
renderer.validateLink = (url) => /^(https?:|mailto:|#|\/)/i.test(url) && !url.startsWith('//')
export const renderMarkdown = (source: string) => renderer.render(source)
export function sourceParts(text: string, start: number, end: number): [string, string, string] {
  const chars = Array.from(text)
  return [
    chars.slice(0, start).join(''),
    chars.slice(start, end).join(''),
    chars.slice(end).join(''),
  ]
}
