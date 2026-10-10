import "./globals.css";
import ThemeProvider from "@/components/ThemeProvider";
import I18nProvider from "@/components/I18nProvider";
import Shell from "@/components/Shell";
import ApplicationBoundary from "@/components/ApplicationBoundary";

const { loadResources, languageMeta } = require("@/lib/i18n/loader");

export const metadata = {
  title: "RSDW Sync",
  description: "Your Dragonwilds worlds, mods, players, and dedicated servers in one RSDW workspace.",
  icons: { icon: "/icon.png" },
};

export default function RootLayout({ children }) {
  const lng = "en";
  const resources = loadResources();
  const { dir } = languageMeta();
  return (
    <html lang={lng} dir={dir} suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Nunito:wght@400;500;600;700;800&display=swap"
          rel="stylesheet"
        />
        {/* Set theme before paint to avoid flash */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('pal-theme')||'dark';if(t==='dark')document.documentElement.classList.add('dark');}catch(e){document.documentElement.classList.add('dark');}})();`,
          }}
        />
      </head>
      <body>
        <I18nProvider lng={lng} resources={resources}>
          <ThemeProvider>
            <ApplicationBoundary>
              <Shell>{children}</Shell>
            </ApplicationBoundary>
          </ThemeProvider>
        </I18nProvider>
      </body>
    </html>
  );
}
