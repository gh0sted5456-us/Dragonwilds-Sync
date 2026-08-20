/* Make the interactive World demo a first-class homepage destination. */
(() => {
  const demo = document.querySelector('.home-demo');
  if (!demo) return;
  demo.id = 'demo-world';

  const nav = document.querySelector('#main-nav');
  if (nav && !nav.querySelector('[href="#demo-world"]')) {
    const servers = nav.querySelector('a[href="servers.html"]');
    const link = document.createElement('a');
    link.href = '#demo-world';
    link.textContent = 'Demo World';
    if (servers?.nextSibling) nav.insertBefore(link, servers.nextSibling);
    else if (servers) servers.insertAdjacentElement('afterend', link);
    else nav.prepend(link);
  }

  const heroActions = document.querySelector('.hero-actions');
  if (heroActions && !heroActions.querySelector('[href="#demo-world"]')) {
    const link = document.createElement('a');
    link.className = 'button button-secondary';
    link.href = '#demo-world';
    link.innerHTML = 'Try Demo World <span aria-hidden="true">↘</span>';
    heroActions.appendChild(link);
  }

  const builder = demo.querySelector('.demo-builder');
  if (builder) {
    builder.id = 'create-server-demo';
    const heading = builder.querySelector('.demo-builder-head h3');
    if (heading) heading.textContent = 'Create a Server — interactive preview';
  }
})();
