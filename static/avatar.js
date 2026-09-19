// Живой аватар Бони: эмоции, моргание, движение рта.
(function () {
  var mouth = document.getElementById('mouth');
  var eyesNormal = document.getElementById('eyesNormal');
  var eyesHappy = document.getElementById('eyesHappy');
  var pupilL = document.getElementById('pupilL');
  var pupilR = document.getElementById('pupilR');
  var cheeks = document.querySelectorAll('.cheek');
  if (!mouth || !eyesNormal) return;

  var talking = false;
  var rafId = null;
  var emotion = 'idle';

  function setMouth(v) {
    v = Math.max(0, Math.min(1, v));
    var h = 7 + v * 30;
    var y = 137 - v * 12;
    mouth.setAttribute('height', h.toFixed(1));
    mouth.setAttribute('y', y.toFixed(1));
    mouth.setAttribute('rx', Math.min(h / 2, 15).toFixed(1));
  }

  function setEmotion(name) {
    emotion = name;
    var happy = (name === 'happy');
    eyesNormal.style.display = happy ? 'none' : '';
    eyesHappy.style.display = happy ? '' : 'none';
    var pupilY = (name === 'thinking') ? 90 : 96;
    if (pupilL) pupilL.setAttribute('cy', pupilY);
    if (pupilR) pupilR.setAttribute('cy', pupilY);
    cheeks.forEach(function (c) { c.setAttribute('opacity', happy ? '0.7' : '0.35'); });
  }

  function blink() {
    if (emotion === 'happy') return;
    eyesNormal.style.transformBox = 'fill-box';
    eyesNormal.style.transformOrigin = 'center';
    eyesNormal.style.transform = 'scaleY(0.08)';
    setTimeout(function () { eyesNormal.style.transform = 'scaleY(1)'; }, 130);
  }

  function scheduleBlink() {
    var t = 1600 + Math.random() * 3200;
    setTimeout(function () { blink(); scheduleBlink(); }, t);
  }

  function startTalking() {
    if (talking) return;
    talking = true;
    var t0 = Date.now();
    (function frame() {
      if (!talking) return;
      var t = (Date.now() - t0) / 1000;
      var v = 0.5 + 0.5 * Math.sin(t * 15) * Math.sin(t * 6.5 + 1.2);
      setMouth(v);
      rafId = requestAnimationFrame(frame);
    })();
  }

  function stopTalking() {
    talking = false;
    if (rafId) cancelAnimationFrame(rafId);
    rafId = null;
    setMouth(0);
  }

  scheduleBlink();
  setEmotion('idle');
  window.BonyaAvatar = {
    startTalking: startTalking,
    stopTalking: stopTalking,
    blink: blink,
    setEmotion: setEmotion
  };
})();
