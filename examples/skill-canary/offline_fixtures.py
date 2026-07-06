#!/usr/bin/env python3
"""Offline dry-run fixtures for the Phase-5 canary HARNESS PLUMBING proof (zero
billables). These are NOT scoring goldens and NOT part of the frozen §7 contract —
they exist so the committed offline test can drive the full harness path (workspace
build → runner subprocess → evidence collection → scorer → budget accounting)
before any real spawn is authorized to run.

GOOD_ARTIFACT passes Check-0 and all 10 checks; POOR_ARTIFACT passes Check-0 but
fails several checks (so an offline pair exercises the margin rule end-to-end).
"""

GOOD_ARTIFACT = {
    "signup/index.html": """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Sign up</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<h1>Create your account</h1>
<img src="logo.svg" alt="Acme logo" width="96" height="96">
<form id="signup">
  <label for="email">Email</label>
  <input id="email" type="email" name="email" autocomplete="email">
  <label for="password">Password</label>
  <input id="password" type="password" name="password" autocomplete="new-password">
  <button type="button" id="toggle" aria-label="Show password">&#128065;</button>
  <button type="submit">Sign up</button>
</form>
<p id="status" role="status" aria-live="polite"></p>
<section aria-labelledby="features-h">
  <h2 id="features-h">Features</h2>
  <ul><li>Fast</li><li>Safe</li><li>Simple</li></ul>
</section>
<script src="app.js"></script>
</body>
</html>
""",
    "signup/style.css": """button, a { touch-action: manipulation; }
input:focus-visible, button:focus-visible { outline: 2px solid #06c; }
""",
    "signup/app.js": """const form = document.getElementById('signup');
const status = document.getElementById('status');
const toggle = document.getElementById('toggle');
const pw = document.getElementById('password');
toggle.addEventListener('click', () => {
  pw.type = pw.type === 'password' ? 'text' : 'password';
});
form.addEventListener('submit', (e) => {
  e.preventDefault();
  status.textContent = 'Signing up…';
  setTimeout(() => { status.textContent = 'Account created.'; }, 1000);
});
""",
}

POOR_ARTIFACT = {
    "signup/index.html": """<!DOCTYPE html>
<html>
<head><title>Sign up</title>
<style>
button { transition: all 0.3s; }
input { outline: none; }
</style>
</head>
<body>
<h1>Sign up</h1>
<img src="logo.png">
<form id="signup">
  Email <input type="email" name="email">
  Password <input type="password" name="password">
  <button type="button" id="toggle">&#128065;</button>
  <button type="submit">Sign up</button>
</form>
<div id="status"></div>
<h3>Features</h3>
<ul><li>Fast</li><li>Safe</li><li>Simple</li></ul>
<script>
const f = document.getElementById('signup');
const s = document.getElementById('status');
document.getElementById('toggle').onclick = function () {
  const p = document.querySelector('input[name=password]');
  p.type = p.type === 'password' ? 'text' : 'password';
};
f.addEventListener('submit', function (e) {
  e.preventDefault();
  s.textContent = 'Signing up...';
  setTimeout(function () { s.textContent = 'Done'; }, 1000);
});
</script>
</body>
</html>
""",
}
