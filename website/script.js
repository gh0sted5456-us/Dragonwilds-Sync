const navToggle = document.querySelector('.nav-toggle');
const nav = document.querySelector('.main-nav');

if (navToggle && nav) {
  navToggle.addEventListener('click', () => {
    const isOpen = nav.classList.toggle('open');
    navToggle.setAttribute('aria-expanded', String(isOpen));
  });

  nav.querySelectorAll('a').forEach((link) => {
    link.addEventListener('click', () => {
      nav.classList.remove('open');
      navToggle.setAttribute('aria-expanded', 'false');
    });
  });
}

const revealItems = document.querySelectorAll('.reveal');
if ('IntersectionObserver' in window) {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12 });

  revealItems.forEach((item) => observer.observe(item));
} else {
  revealItems.forEach((item) => item.classList.add('visible'));
}

const placard = document.querySelector('.placard');
if (placard) {
  placard.addEventListener('click', () => placard.classList.toggle('flipped'));
}

const releaseVersion = document.getElementById('release-version');
const releaseDate = document.getElementById('release-date');
const releaseChannel = document.getElementById('release-channel');
const releaseLink = document.getElementById('release-link');

async function loadLatestRelease() {
  try {
    const response = await fetch('https://api.github.com/repos/gh0sted5456-us/Dragonwilds-Sync/releases/latest', {
      headers: { 'Accept': 'application/vnd.github+json' }
    });

    if (!response.ok) throw new Error('No public release available');

    const release = await response.json();
    const date = new Date(release.published_at || release.created_at);

    releaseVersion.textContent = release.tag_name || release.name || 'Latest';
    releaseDate.textContent = Number.isNaN(date.getTime())
      ? 'GitHub Releases'
      : date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
    releaseChannel.textContent = release.prerelease ? 'Pre-release' : 'Stable';
    releaseLink.href = release.html_url || releaseLink.href;
  } catch (_) {
    releaseVersion.textContent = 'Latest available';
    releaseDate.textContent = 'GitHub Releases';
    releaseChannel.textContent = 'Development';
  }
}

loadLatestRelease();
