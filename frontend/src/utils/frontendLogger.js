import { config } from '@/config'

const ACTION_SELECTOR = [
  'button',
  'a[href]',
  '[role="button"]',
  '.el-button',
  '.el-menu-item',
  '.el-tabs__item',
  'input[type="button"]',
  'input[type="submit"]',
  'input[type="checkbox"]',
  'input[type="radio"]',
  'select',
].join(',')

function compactText(text) {
  return (text || '').replace(/\s+/g, ' ').trim().slice(0, 120)
}

function describeTarget(el) {
  if (!el) return {}
  return {
    target: el.getAttribute('data-log-id') || el.getAttribute('aria-label') || el.tagName.toLowerCase(),
    label: compactText(el.innerText || el.value || el.getAttribute('title') || el.getAttribute('placeholder')),
    action: el.getAttribute('data-action') || el.getAttribute('type') || undefined,
  }
}

function postFrontendEvent(payload) {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 1500)
  const body = JSON.stringify({
    path: window.location.pathname + window.location.search,
    ...payload,
  })
  const url = `${config.api.baseUrl}/frontend-events/log`

  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
    keepalive: true,
    signal: controller.signal,
  }).catch(() => {}).finally(() => window.clearTimeout(timeout))
}

export function installFrontendActionLogger(router) {
  document.addEventListener('click', (event) => {
    const target = event.target?.closest?.(ACTION_SELECTOR)
    if (!target) return
    postFrontendEvent({
      event_type: 'click',
      ...describeTarget(target),
    })
  }, true)

  document.addEventListener('submit', (event) => {
    postFrontendEvent({
      event_type: 'submit',
      ...describeTarget(event.target),
    })
  }, true)

  document.addEventListener('change', (event) => {
    const target = event.target?.closest?.('select,input[type="checkbox"],input[type="radio"],.el-switch input')
    if (!target) return
    postFrontendEvent({
      event_type: 'change',
      ...describeTarget(target),
    })
  }, true)

  router.afterEach((to, from) => {
    if (to.fullPath === from.fullPath) return
    postFrontendEvent({
      event_type: 'route',
      target: 'router',
      label: `${from.fullPath || '-'} -> ${to.fullPath}`,
    })
  })
}
