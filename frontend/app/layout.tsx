import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'Mira — A warmer welcome | Mehman', description: 'Your personal Goa stay, thoughtfully arranged. Fictional hotel receptionist case study.' };
export default function RootLayout({ children }: { children: React.ReactNode }) { return <html lang="en"><body>{children}</body></html>; }
