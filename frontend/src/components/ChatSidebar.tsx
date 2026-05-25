import { useState, useRef, useEffect } from "react";
import { Message } from "@/app/page";
import { Send, Bot, User, AlertTriangle } from "lucide-react";

interface ChatSidebarProps {
  messages: Message[];
  onSendMessage: (msg: string) => void;
  isLoading: boolean;
}

export default function ChatSidebar({ messages, onSendMessage, isLoading }: ChatSidebarProps) {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    onSendMessage(input);
    setInput("");
  };

  return (
    <div className="flex flex-col h-full w-full relative bg-zinc-50">
      <div className="p-4 border-b border-zinc-200 bg-white z-10 shadow-sm flex items-center justify-between">
        <div>
          <h1 className="font-semibold text-zinc-800 text-lg">Legal Assistant</h1>
          <p className="text-xs text-zinc-500">Powered by supportLegal RAG</p>
        </div>
        <div className="h-8 w-8 bg-blue-600 rounded-lg flex items-center justify-center">
          <Bot size={18} className="text-white" />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center px-4">
            <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mb-4">
              <Bot size={32} className="text-blue-600" />
            </div>
            <h2 className="text-xl font-semibold text-zinc-800 mb-2">Xin chào!</h2>
            <p className="text-zinc-500 text-sm max-w-sm leading-relaxed">
              Tôi là trợ lý pháp lý ảo. Hãy đặt câu hỏi về luật pháp Việt Nam, tôi sẽ phân tích dựa trên văn bản pháp luật hiện hành theo cấu trúc IRAC.
            </p>
          </div>
        ) : (
          messages.map((msg, idx) => (
            <div key={idx} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`flex max-w-[85%] gap-3 ${msg.role === "user" ? "flex-row-reverse" : "flex-row"}`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
                  msg.role === "user" ? "bg-zinc-200" : "bg-blue-600"
                }`}>
                  {msg.role === "user" ? <User size={16} className="text-zinc-600"/> : <Bot size={16} className="text-white"/>}
                </div>
                <div className={`p-4 rounded-2xl ${
                  msg.role === "user" 
                    ? "bg-zinc-800 text-white rounded-tr-sm" 
                    : "bg-white border border-zinc-200 text-zinc-800 shadow-sm rounded-tl-sm"
                }`}>
                  {/* Domains/Badges */}
                  {msg.role === "agent" && msg.domains && msg.domains.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mb-2.5">
                      {msg.domains.map((domain) => {
                        let label = domain;
                        let colorClass = "bg-zinc-100 text-zinc-600 border-zinc-200";
                        
                        // Mapping English IDs from Classifier to Vietnamese Labels & Styles
                        if (domain === "Criminal") {
                          label = "Hình sự";
                          colorClass = "bg-red-50 text-red-600 border-red-100";
                        } else if (domain === "Civil & Family") {
                          label = "Dân sự";
                          colorClass = "bg-blue-50 text-blue-600 border-blue-100";
                        } else if (domain === "Administrative & Tax") {
                          label = "Hành chính";
                          colorClass = "bg-amber-50 text-amber-600 border-amber-100";
                        } else if (domain === "Business & Commercial") {
                          label = "Kinh doanh";
                          colorClass = "bg-emerald-50 text-emerald-600 border-emerald-100";
                        } else if (domain === "Labor & Insurance") {
                          label = "Lao động";
                          colorClass = "bg-indigo-50 text-indigo-600 border-indigo-100";
                        } else if (domain === "Land & Real Estate") {
                          label = "Đất đai";
                          colorClass = "bg-orange-50 text-orange-600 border-orange-100";
                        }
                        
                        return (
                          <span key={domain} className={`px-2 py-0.5 rounded text-[10px] font-bold border uppercase tracking-wider ${colorClass}`}>
                            {label}
                          </span>
                        );
                      })}
                    </div>
                  )}

                  <div className="text-sm whitespace-pre-wrap leading-relaxed font-sans">
                    {msg.content}
                    {msg.streaming && (
                      <span className="inline-block w-1.5 h-4 ml-1 bg-blue-600 animate-pulse align-middle" />
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))
        )}
        
        <div ref={messagesEndRef} />
      </div>

      <div className="p-4 bg-white border-t border-zinc-200 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.05)]">
        <form onSubmit={handleSubmit} className="relative flex items-center">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Nhập câu hỏi pháp lý..."
            className="w-full bg-zinc-100 border border-transparent focus:bg-white focus:border-blue-500 focus:ring-2 focus:ring-blue-100 outline-none rounded-full py-3.5 pl-5 pr-14 text-sm transition-all text-zinc-800 placeholder-zinc-400"
            disabled={isLoading}
          />
          <button 
            type="submit" 
            disabled={!input.trim() || isLoading}
            className="absolute right-1.5 p-2.5 bg-blue-600 text-white rounded-full hover:bg-blue-700 disabled:opacity-50 disabled:hover:bg-blue-600 transition-colors"
          >
            <Send size={18} className="ml-0.5" />
          </button>
        </form>
        <div className="flex items-center justify-center gap-1.5 mt-3 text-[11px] text-amber-600 bg-amber-50/80 py-1.5 px-3 rounded text-center">
          <AlertTriangle size={12} className="shrink-0" />
          <span>
            <strong>Lưu ý:</strong> Thông tin này chỉ mang tính chất tham khảo, không thay thế cho tư vấn pháp lý chuyên nghiệp.
          </span>
        </div>
      </div>
    </div>
  );
}
