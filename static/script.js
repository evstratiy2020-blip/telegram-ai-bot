// Сайт Бони: настоящий ИИ + голос Бони + пение. Доступ: Telegram или пароль.

var messages = document.getElementById('messages');
var input = document.getElementById('input');
var send = document.getElementById('send');
var voiceBtn = document.getElementById('voiceBtn');
var soundBtn = document.getElementById('soundBtn');
var singBtn = document.getElementById('singBtn');

var tg = window.Telegram && window.Telegram.WebApp;
if (tg) { try { tg.ready(); tg.expand(); } catch (e) {} }
var initData = (tg && tg.initData) ? tg.initData : '';
var appKey = '';
try {
  var m = location.search.match(/[?&]k=([^&]+)/);
  if (m) appKey = decodeURIComponent(m[1]);
} catch (e) {}

var chatHistory = [];
var soundOn = true;
var busy = false;
var unlocked = false;
var currentAudio = null;
var singMode = false;

var dbgEl = document.getElementById('dbg');
function dbg(msg) { if (dbgEl) dbgEl.textContent = msg; }

function authHeaders() {
  var h = { 'Content-Type': 'application/json' };
  if (initData) h['X-Init-Data'] = initData;
  return h;
}

var voiceKey = 'bonya';
function voiceUrl(text) { return '/api/voice?text=' + encodeURIComponent(text) + '&voice=' + voiceKey; }
function singUrl(text) {
  var el = document.getElementById('musicStyle');
  var st = el ? el.value : 'none';
  return '/api/sing?text=' + encodeURIComponent(text) + '&style=' + encodeURIComponent(st) + '&voice=' + voiceKey;
}

/* ---------- Вход ---------- */
var loginEl = document.getElementById('login');
var passwordEl = document.getElementById('password');
var loginBtn = document.getElementById('loginBtn');
var loginErr = document.getElementById('loginErr');

function showLogin() { if (loginEl) loginEl.classList.remove('hidden'); }
function hideLogin() { if (loginEl) loginEl.classList.add('hidden'); }

async function doLogin() {
  if (loginErr) loginErr.textContent = '';
  try {
    var r = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: passwordEl.value })
    });
    if (r.ok) {
      hideLogin();
      passwordEl.value = '';
      input.focus();
    } else if (loginErr) {
      loginErr.textContent = 'Неверный пароль';
    }
  } catch (e) {
    if (loginErr) loginErr.textContent = 'Ошибка сети';
  }
}
if (loginBtn) loginBtn.addEventListener('click', doLogin);
if (passwordEl) passwordEl.addEventListener('keydown', function (e) { if (e.key === 'Enter') doLogin(); });

async function checkAuth() {
  try {
    var h = initData ? { 'X-Init-Data': initData } : {};
    var r = await fetch('/api/me' + (appKey ? '?k=' + encodeURIComponent(appKey) : ''), { headers: h });
    if (r.ok) { hideLogin(); return; }
    if (loginErr) loginErr.textContent = 'tg=' + (tg ? 'да' : 'нет') + ', initData=' + (initData ? initData.length : 0) + ', код ' + r.status;
    showLogin();
  } catch (e) {
    if (loginErr) loginErr.textContent = 'ошибка сети: ' + e;
    showLogin();
  }
}

/* ---------- Звук/аватар ---------- */
function unlockAudio() {
  if (unlocked) return;
  unlocked = true;
  try {
    var a = new Audio('silent.mp3');
    a.volume = 0;
    a.play().catch(function () {});
  } catch (e) {}
}

function addMessage(text, who, audio) {
  var el = document.createElement('div');
  el.className = 'msg ' + who;
  var span = document.createElement('span');
  span.textContent = text;
  el.appendChild(span);
  if (who === 'bot' && audio) {
    var btn = document.createElement('button');
    btn.className = 'play';
    btn.textContent = '🔊';
    btn.addEventListener('click', function () { unlockAudio(); playVoice(audio, text); });
    el.appendChild(btn);
  }
  messages.appendChild(el);
  messages.scrollTop = messages.scrollHeight;
  return el;
}

function fallbackTalk(text) {
  if (!window.BonyaAvatar) return;
  var ms = Math.min(9000, 900 + (text ? text.length * 75 : 1500));
  window.BonyaAvatar.startTalking();
  setTimeout(function () { window.BonyaAvatar.stopTalking(); }, ms);
}

var activeAudios = [];

function stopAllAudio() {
  for (var i = 0; i < activeAudios.length; i++) {
    try { activeAudios[i].pause(); activeAudios[i].currentTime = 0; } catch (e) {}
  }
  activeAudios = [];
  currentAudio = null;
  if (window.BonyaAvatar) window.BonyaAvatar.stopTalking();
}

function playVoice(url, text) {
  try {
    stopAllAudio();
    var audio = new Audio(url);
    activeAudios.push(audio);
    currentAudio = audio;
    var started = false;
    function beginTalk() { started = true; botSpeaking = true; if (window.BonyaAvatar) window.BonyaAvatar.startTalking(); }
    audio.onplay = beginTalk;
    audio.onplaying = beginTalk;
    audio.onended = function () {
      var i = activeAudios.indexOf(audio); if (i >= 0) activeAudios.splice(i, 1);
      if (window.BonyaAvatar) window.BonyaAvatar.stopTalking();
      botSpeaking = false;
      restartMicSoon();
    };
    audio.onerror = function () {
      var i = activeAudios.indexOf(audio); if (i >= 0) activeAudios.splice(i, 1);
      botSpeaking = false;
      restartMicSoon();
      if (!started) fallbackTalk(text);
    };
    var p = audio.play();
    if (p && p.catch) p.catch(function () { if (!started) fallbackTalk(text); });
  } catch (e) {
    fallbackTalk(text);
  }
}

function stopAudio() {
  stopAllAudio();
}

function singText(text) {
  unlockAudio();
  stopAllAudio();
  if (window.BonyaAvatar) window.BonyaAvatar.setEmotion('happy');
  var audio = new Audio(singUrl(text));
  activeAudios.push(audio);
  currentAudio = audio;
  audio.onplaying = function () { if (window.BonyaAvatar) window.BonyaAvatar.startTalking(); };
  audio.onended = function () {
    if (window.BonyaAvatar) { window.BonyaAvatar.stopTalking(); window.BonyaAvatar.setEmotion('idle'); }
  };
  audio.onerror = function () { if (window.BonyaAvatar) window.BonyaAvatar.setEmotion('idle'); };
  var p = audio.play();
  if (p && p.catch) p.catch(function () {});
}

/* ---------- Чат ---------- */
async function sendMessage() {
  var text = input.value.trim();
  if (!text || busy) return;
  if (singMode) {
    input.value = '';
    addMessage(text, 'user');
    singText(text);
    return;
  }
  unlockAudio();
  input.value = '';
  addMessage(text, 'user');
  chatHistory.push({ role: 'user', content: text });
  if (chatHistory.length > 20) chatHistory = chatHistory.slice(-20);

  busy = true;
  send.disabled = true;
  if (window.BonyaAvatar) window.BonyaAvatar.setEmotion('thinking');
  var pending = addMessage('Боня печатает…', 'bot');
  pending.classList.add('typing');

  try {
    var resp = await fetch('/api/chat', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ messages: chatHistory })
    });
    if (resp.status === 403) {
      if (pending.parentNode) pending.remove();
      addMessage('Нет доступа. Открой чат через бота или войди по паролю.', 'bot');
      busy = false; send.disabled = false;
      return;
    }
    var data = await resp.json();
    if (pending.parentNode) pending.remove();
    var reply = data.reply || data.error || 'Не получилось ответить 😔';
    addMessage(reply, 'bot', voiceUrl(reply));
    chatHistory.push({ role: 'assistant', content: reply });
    if (window.BonyaAvatar) window.BonyaAvatar.setEmotion('happy');
    setTimeout(function () { if (window.BonyaAvatar) window.BonyaAvatar.setEmotion('idle'); }, 1600);
    if (window.BonyaAvatar) window.BonyaAvatar.startTalking();
    if (soundOn) {
      playVoice(voiceUrl(reply), reply);
    } else {
      var estMs = Math.min(20000, 1500 + reply.length * 80);
      setTimeout(function () { if (window.BonyaAvatar) window.BonyaAvatar.stopTalking(); restartMicSoon(); }, estMs);
    }
  } catch (err) {
    if (pending.parentNode) pending.remove();
    addMessage('Ошибка связи с сервером 😔', 'bot');
  }
  busy = false;
  send.disabled = false;
  input.focus();
}

send.addEventListener('click', sendMessage);
input.addEventListener('keydown', function (e) { if (e.key === 'Enter') sendMessage(); });

if (voiceBtn) voiceBtn.addEventListener('click', function () {
  unlockAudio();
  soundOn = !soundOn;
  if (!soundOn) stopAudio();
  voiceBtn.classList.toggle('on', soundOn);
  soundBtn.classList.toggle('on', soundOn);
});

soundBtn.addEventListener('click', function () {
  unlockAudio();
  soundOn = !soundOn;
  if (!soundOn) stopAudio();
  voiceBtn.classList.toggle('on', soundOn);
  soundBtn.classList.toggle('on', soundOn);
});

if (singBtn) singBtn.addEventListener('click', function () {
  unlockAudio();
  singMode = !singMode;
  singBtn.classList.toggle('on', singMode);
  if (window.BonyaAvatar) window.BonyaAvatar.setEmotion(singMode ? 'happy' : 'idle');
});

var micBtn = document.getElementById('micBtn');
var recognition = null;
var micOn = false;
var botSpeaking = false;
var SR = window.SpeechRecognition || window.webkitSpeechRecognition;

function restartMicSoon() {
  if (!micOn || !recognition || botSpeaking) return;
  setTimeout(function () {
    if (micOn && !botSpeaking) { try { recognition.start(); } catch (e) {} }
  }, 400);
}

if (SR) {
  recognition = new SR();
  recognition.lang = 'ru-RU';
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  recognition.onresult = function (e) {
    var text = e.results[0][0].transcript;
    if (text) { input.value = text; sendMessage(); }
  };
  recognition.onend = function () { micOn = false; if (micBtn) micBtn.classList.remove('on'); };
  recognition.onerror = function () { micOn = false; if (micBtn) micBtn.classList.remove('on'); };
}
if (micBtn) {
  micBtn.addEventListener('click', function () {
    unlockAudio();
    if (!recognition) { addMessage('Голосовой ввод не поддерживается в этом браузере 😔', 'bot'); return; }
    if (micOn) {
      micOn = false;
      micBtn.classList.remove('on');
      try { recognition.stop(); } catch (e) {}
    } else {
      micOn = true;
      micBtn.classList.add('on');
      try { recognition.start(); } catch (e) { micOn = false; micBtn.classList.remove('on'); }
    }
  });
}

if (voiceBtn) voiceBtn.classList.add('on');
if (soundBtn) soundBtn.classList.add('on');

/* ================= ГОЛОС ================= */
var VOICES = [
  { key: 'male', name: 'Мужской' },
  { key: 'male_low', name: 'Мужской низкий' },
  { key: 'female', name: 'Женский' },
  { key: 'bonya', name: 'Боня' },
  { key: 'mono', name: 'Робот-монотонный' }
];
var voicePanel = document.getElementById('voicePanel');
var voiceListEl = document.getElementById('voiceList');

function renderVoices() {
  if (!voiceListEl) return;
  voiceListEl.innerHTML = VOICES.map(function (v) {
    return '<button class="voice-btn ' + (v.key === voiceKey ? 'on' : '') + '" data-v="' + v.key + '">🎤 ' + v.name + '</button>';
  }).join('');
  Array.prototype.forEach.call(voiceListEl.querySelectorAll('.voice-btn'), function (b) {
    b.addEventListener('click', function () {
      voiceKey = b.dataset.v;
      renderVoices();
      var cv = document.getElementById('cartoonVoice');
      if (cv) cv.value = voiceKey;
      if (voicePanel) voicePanel.classList.add('hidden');
    });
  });
}
renderVoices();

var voicePickBtn = document.getElementById('voicePickBtn');
if (voicePickBtn) voicePickBtn.addEventListener('click', function () {
  unlockAudio();
  if (voicePanel) voicePanel.classList.toggle('hidden');
  var cart = document.getElementById('cartoon');
  if (cart) cart.classList.add('hidden');
});

/* ================= МУЛЬТИК ================= */
var CHAR_COUNT = 9;
var LEVELS = 6;
var currentChar = 8;
var cartoonEl = document.getElementById('cartoon');
var cartoonImg = document.getElementById('cartoonImg');
var cartoonChars = document.getElementById('cartoonChars');
var cartoonVoice = document.getElementById('cartoonVoice');
var cartoonMusic = document.getElementById('cartoonMusic');
var cartoonText = document.getElementById('cartoonText');

function setLevel(lvl) {
  var f = Math.max(0, Math.min(LEVELS - 1, Math.round(lvl * (LEVELS - 1))));
  if (cartoonImg) cartoonImg.src = 'mult/c' + currentChar + '_' + f + '.png';
}

if (cartoonChars) {
  var h = '';
  for (var i = 0; i < CHAR_COUNT; i++) {
    h += '<button class="charbtn ' + (i === currentChar ? 'on' : '') + '" data-c="' + i + '"><img src="mult/c' + i + '_0.png" alt=""></button>';
  }
  cartoonChars.innerHTML = h;
  Array.prototype.forEach.call(cartoonChars.querySelectorAll('.charbtn'), function (b) {
    b.addEventListener('click', function () {
      currentChar = parseInt(b.dataset.c, 10);
      setLevel(0);
      Array.prototype.forEach.call(cartoonChars.querySelectorAll('.charbtn'), function (x) { x.classList.remove('on'); });
      b.classList.add('on');
    });
  });
}

if (cartoonVoice) {
  cartoonVoice.innerHTML = VOICES.map(function (v) {
    return '<option value="' + v.key + '"' + (v.key === voiceKey ? ' selected' : '') + '>' + v.name + '</option>';
  }).join('');
  cartoonVoice.addEventListener('change', function () { voiceKey = cartoonVoice.value; renderVoices(); });
}

var actx = null, cartAudio = null, cartRaf = null;

function audioCtx() {
  if (!actx) {
    var AC = window.AudioContext || window.webkitAudioContext;
    actx = new AC();
  }
  return actx;
}

function stopCartoon() {
  if (cartAudio) { try { cartAudio.pause(); } catch (e) {} cartAudio = null; }
  if (cartRaf) cancelAnimationFrame(cartRaf);
  cartRaf = null;
  setLevel(0);
}

function playCartoon(url) {
  stopAudio();
  stopCartoon();
  unlockAudio();
  var c = audioCtx();
  if (c.state === 'suspended') c.resume();
  var audio = new Audio(url);
  cartAudio = audio;
  try {
    var src = c.createMediaElementSource(audio);
    var an = c.createAnalyser();
    an.fftSize = 512;
    src.connect(an);
    an.connect(c.destination);
    var data = new Uint8Array(an.frequencyBinCount);
    function loop() {
      an.getByteFrequencyData(data);
      var sum = 0;
      for (var i = 0; i < data.length; i++) sum += data[i];
      setLevel(Math.min(1, (sum / data.length) / 55));
      cartRaf = requestAnimationFrame(loop);
    }
    audio.onplay = loop;
    audio.onended = function () { if (cartRaf) cancelAnimationFrame(cartRaf); cartRaf = null; setLevel(0); };
  } catch (e) {
    audio.onplay = function () { window.BonyaAvatar && window.BonyaAvatar.startTalking(); };
    audio.onended = function () { window.BonyaAvatar && window.BonyaAvatar.stopTalking(); setLevel(0); };
  }
  audio.onerror = function () { setLevel(0); };
  var p = audio.play();
  if (p && p.catch) p.catch(function () {});
}

var cartoonBtn = document.getElementById('cartoonBtn');
var cartoonClose = document.getElementById('cartoonClose');
var speakBtn = document.getElementById('speakBtn');
var singBtn2 = document.getElementById('singBtn2');

if (cartoonBtn) cartoonBtn.addEventListener('click', function () {
  unlockAudio();
  if (voicePanel) voicePanel.classList.add('hidden');
  if (cartoonEl) cartoonEl.classList.remove('hidden');
  setLevel(0);
});
if (cartoonClose) cartoonClose.addEventListener('click', function () {
  stopCartoon();
  if (cartoonEl) cartoonEl.classList.add('hidden');
});
if (speakBtn) speakBtn.addEventListener('click', function () {
  var t = (cartoonText.value || '').trim();
  if (!t) { cartoonText.focus(); return; }
  playCartoon('/api/voice?text=' + encodeURIComponent(t) + '&voice=' + voiceKey);
});
if (singBtn2) singBtn2.addEventListener('click', function () {
  var t = (cartoonText.value || '').trim();
  if (!t) { cartoonText.focus(); return; }
  var st = cartoonMusic ? cartoonMusic.value : 'none';
  playCartoon('/api/sing?text=' + encodeURIComponent(t) + '&style=' + encodeURIComponent(st) + '&voice=' + voiceKey);
});

setInterval(function () {
  if (cartAudio && !cartAudio.paused) return;
  if (!cartoonEl || cartoonEl.classList.contains('hidden')) return;
  if (cartoonImg) cartoonImg.src = 'mult/c' + currentChar + '_blink.png';
  setTimeout(function () { if (!(cartAudio && !cartAudio.paused)) setLevel(0); }, 150);
}, 4200);

addMessage('Привет! Я Боня — твой живой ИИ-помощник. Спроси меня о чём-нибудь! 🤖', 'bot', voiceUrl('Привет! Я Боня. Спроси меня о чём-нибудь!'));
checkAuth();
input.focus();
