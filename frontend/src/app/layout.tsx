import type { Metadata } from "next";
import "@ant-design/v5-patch-for-react-19";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "大学校园多智能体平台",
  description: "公选课推荐 / 智能对话 / 成绩报告 / 评价寄语 / 知识库",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // suppressHydrationWarning：NightEye 等浏览器扩展会在水合前给 <html>/<body> 注入
    // nighteye 等属性，导致服务端 HTML 与客户端 props 不匹配刷 Console Error。勿删。
    // （只跳过该元素自身属性层的告警，不影响子节点内容校验，不会掩盖真实 mismatch）
    <html
      lang="zh-CN"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="min-h-full flex flex-col" suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}
