export const metadata = {
  title: 'Image to Vector',
  description: 'Internal image-to-vector pipeline app',
};

import './globals.css';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
