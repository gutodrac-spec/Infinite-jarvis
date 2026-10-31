// Service worker: transforma o push do Jarvis numa notificação de chamada.
self.addEventListener('push', (event) => {
  const data = event.data ? event.data.json() : {}
  event.waitUntil(
    self.registration.showNotification(data.title || 'Jarvis', {
      body: data.body || '',
      icon: 'icon.svg',
      tag: 'jarvis-call',
      renotify: true,
      requireInteraction: true,
      vibrate: [600, 200, 600, 200, 600, 200, 600],
      data: { url: data.url || './' },
      actions: [{ action: 'answer', title: 'Atender' }],
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = event.notification.data.url
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((wins) => {
      for (const w of wins) if ('navigate' in w) return w.navigate(url).then((c) => c && c.focus())
      return clients.openWindow(url)
    }),
  )
})
