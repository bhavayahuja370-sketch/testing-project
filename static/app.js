const chatForm = document.querySelector('#chatForm');
const input = document.querySelector('#messageInput');
const messages = document.querySelector('#messages');
const welcome = document.querySelector('#welcome');
const subject = document.querySelector('#subject');
const level = document.querySelector('#level');
const themeToggle = document.querySelector('#themeToggle');
const modelSelect = document.querySelector('#modelSelect');

modelSelect.value = sessionStorage.getItem('nova-model') || 'gemini';
modelSelect.addEventListener('change', () => sessionStorage.setItem('nova-model', modelSelect.value));

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem('nova-theme', theme);
  const dark = theme === 'dark';
  themeToggle.setAttribute('aria-label', `Switch to ${dark ? 'light' : 'dark'} mode`);
  themeToggle.title = themeToggle.getAttribute('aria-label');
}

setTheme(localStorage.getItem('nova-theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));
themeToggle.addEventListener('click', () => setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));

function addMessage(text, role, typing = false, scroll = true) {
  const item = document.createElement('div');
  item.className = `message ${role}${typing ? ' typing' : ''} message-enter`;
  if (role === 'assistant') item.innerHTML = '<div class="bot-avatar">✦</div>';
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = text;
  item.appendChild(bubble);
  messages.appendChild(item);
  if (scroll) item.scrollIntoView({ behavior: 'smooth', block: 'end' });
  return item;
}

async function loadRecentChat() {
  try {
    const response = await fetch('/api/history');
    if (!response.ok) return;
    const data = await response.json();
    if (!Array.isArray(data.messages) || !data.messages.length) return;
    welcome.style.display = 'none';
    data.messages.forEach(message => {
      if (message && ['user', 'assistant'].includes(message.role) && typeof message.content === 'string') {
        addMessage(message.content, message.role, false, false);
      }
    });
    messages.lastElementChild?.scrollIntoView({ behavior: 'auto', block: 'end' });
  } catch (_) {
    // An empty history or unavailable database should not prevent a new chat.
  }
}

async function sendMessage(value) {
  const text = value.trim();
  if (!text) return;
  welcome.style.display = 'none';
  addMessage(text, 'user');
  input.value = ''; input.style.height = 'auto';
  const indicator = addMessage('Nova is thinking…', 'assistant', true);
  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: text, subject: subject.value, level: level.value, model: modelSelect.value}),
    });
    const data = await res.json().catch(() => ({}));
    indicator.remove();
    addMessage(data.reply || data.error || 'I could not generate a response.', 'assistant');
  } catch (_) {
    indicator.remove(); addMessage('I’m having trouble connecting. Please try again.', 'assistant');
  }
}

chatForm.addEventListener('submit', e => { e.preventDefault(); sendMessage(input.value); });
document.querySelectorAll('[data-prompt]').forEach(button => button.addEventListener('click', () => sendMessage(button.dataset.prompt)));
input.addEventListener('input', () => { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 120) + 'px'; });
input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); chatForm.requestSubmit(); }});
document.querySelector('#newChat').addEventListener('click', () => { messages.innerHTML = ''; welcome.style.display = ''; input.focus(); });

const modal = document.querySelector('#flashcardModal');
document.querySelector('#flashcardButton').addEventListener('click', () => modal.showModal());
document.querySelector('#closeModal').addEventListener('click', () => modal.close());
document.querySelector('#flashcardForm').addEventListener('submit', async e => {
  e.preventDefault(); const topic = document.querySelector('#flashcardTopic').value;
  const res = await fetch('/api/flashcards', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({topic})});
  const data = await res.json();
  document.querySelector('#cards').innerHTML = data.cards.map(card => `<div class="flashcard"><strong>${card.front}</strong><span>${card.back}</span></div>`).join('');
});

loadRecentChat();
