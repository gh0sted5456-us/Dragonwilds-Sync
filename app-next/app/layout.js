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
        {/* Set theme before paint to avoid flash */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){var t='dark';try{t=localStorage.getItem('rsdw-theme')||'dark';}catch(e){}if(['dark','gilded','amethyst','ember','frost'].indexOf(t)<0)t='dark';document.documentElement.classList.add('dark');document.documentElement.dataset.rsdwTheme=t;if(window.desktop?.nativeSplash)document.documentElement.dataset.rsdwNativeSplash='true';})();`,
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
