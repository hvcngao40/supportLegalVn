"use client";

import { useState } from "react";
import MainPane from "@/components/MainPane";
import ChatSidebar from "@/components/ChatSidebar";
import { buildApiUrl } from "@/lib/apiBaseUrl";

export interface Citation {
  source?: string;
  article_uuid?: string;
  text: string;
  score?: number;
  metadata?: {
    source: string;
    file_name: string;
    article_title?: string;
    chapter_title?: string;
    part_title?: string;
  };
}

export interface Message {
  role: "user" | "agent";
  content: string;
  streaming?: boolean;
  domains?: string[];
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const encodeBase64 = (value: string) => {
    const bytes = new TextEncoder().encode(value);
    let binary = "";
    bytes.forEach((b) => {
      binary += String.fromCharCode(b);
    });
    return btoa(binary);
  };

  const handleSendMessage = async (content: string) => {
    // Keep a sliding window of the last 4 messages (2 turns)
    const chatHistoryWindow = messages.slice(-4);
    
    // 1. Add BOTH user and placeholder agent message in ONE go to avoid race conditions
    setMessages(prev => [
      ...prev, 
      { role: "user", content },
      { role: "agent", content: "", streaming: true }
    ]);
    
    setIsLoading(true);
    setCitations([]); 

    try {
      const encodedHistory = encodeBase64(JSON.stringify(chatHistoryWindow));
      const url = new URL(buildApiUrl("/api/v1/stream"));
      url.searchParams.set("query", content);
      if (chatHistoryWindow.length > 0) {
        url.searchParams.set("chat_history", encodedHistory);
      }

      await new Promise<void>((resolve, reject) => {
        const eventSource = new EventSource(url.toString());

        eventSource.onmessage = (message) => {
          try {
            const event = JSON.parse(message.data);

            if (event.type === "padding") {
              return;
            } else if (event.type === "citations") {
              setCitations(event.data || []);
            } else if (event.type === "token") {
              setMessages(prev => {
                const next = [...prev];
                const last = next[next.length - 1];
                if (last && last.role === "agent") {
                  next[next.length - 1] = { ...last, content: (last.content || "") + event.content };
                }
                return next;
              });
            } else if (event.type === "classification") {
              setMessages(prev => {
                const next = [...prev];
                const last = next[next.length - 1];
                if (last && last.role === "agent") {
                  next[next.length - 1] = { ...last, domains: event.domains };
                }
                return next;
              });
            } else if (event.type === "error") {
              eventSource.close();
              reject(new Error(event.content || "Lỗi stream từ server"));
            } else if (event.type === "done") {
              setMessages(prev => {
                const next = [...prev];
                const last = next[next.length - 1];
                if (last && last.role === "agent") {
                  next[next.length - 1] = { ...last, streaming: false };
                }
                return next;
              });
              eventSource.close();
              resolve();
            }
          } catch (e) {
            console.error("Failed to parse SSE JSON:", e, message.data);
          }
        };

        eventSource.onerror = () => {
          eventSource.close();
          reject(new Error("Stream connection failed"));
        };
      });
    } catch (error) {
      console.error(error);
      setMessages((prev) => {
        const newMsgs = [...prev];
        const lastMsg = newMsgs[newMsgs.length - 1];
        if (lastMsg && lastMsg.role === "agent") {
          lastMsg.content = `Lỗi: ${error instanceof Error ? error.message : "Kết nối thất bại"}. Vui lòng thử lại.`;
          lastMsg.streaming = false;
        }
        return newMsgs;
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-screen w-full bg-zinc-50 overflow-hidden font-sans" suppressHydrationWarning>
      {/* Left Pane - Context Retrieval */}
      <div className="w-1/2 h-full border-r border-zinc-200 bg-white">
        <MainPane citations={citations} />
      </div>

      {/* Right Pane - Chat Interface */}
      <div className="w-1/2 h-full bg-zinc-50 flex flex-col">
        <ChatSidebar 
          messages={messages} 
          citations={citations}
          onSendMessage={handleSendMessage}
          isLoading={isLoading} 
        />
      </div>
    </div>
  );
}
