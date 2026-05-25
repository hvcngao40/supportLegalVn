/**
 * Phase 19 Frontend Integration Example
 *
 * Example Next.js component showing how to:
 * 1. Receive "ready_for_llm" response from backend
 * 2. Handle the prompt + retrievals
 * 3. Send prompt to external LLM (OpenAI/Gemini)
 * 4. Display results to user
 */

'use client';

import React, { useState, useEffect } from 'react';

interface Retrieval {
  source: string;
  text: string;
  score: number;
  article_uuid: string;
}

interface RAGResponse {
  status: 'ready_for_llm';
  prompt: string;
  retrievals: Retrieval[];
  metadata: {
    cache_hit: boolean;
    used_cache_threshold: number;
  };
}

interface MessageRole {
  role: 'user' | 'assistant';
  content: string;
}

/**
 * LegalRAGChat - Example component for Phase 19 integration
 *
 * Usage:
 * - Send user query to backend `/api/v1/ask` with ENABLE_LLM_GENERATION=false
 * - Receive "ready_for_llm" response with prompt
 * - Component handles sending prompt to OpenAI/Gemini
 * - Display results to user
 */
export const LegalRAGChat: React.FC = () => {
  const [userQuery, setUserQuery] = useState('');
  const [chatHistory, setChatHistory] = useState<MessageRole[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [showRetrievals, setShowRetrievals] = useState(false);
  const [cacheHit, setCacheHit] = useState(false);
  const [retrievals, setRetrievals] = useState<Retrieval[]>([]);
  const [selectedRetrievalIdx, setSelectedRetrievalIdx] = useState<number>(0);
  const [copiedNotice, setCopiedNotice] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [dontShowAgain, setDontShowAgain] = useState(false);

  /**
   * Phase 1: Send query to backend RAG pipeline
   * Backend returns prompt + retrievals (NOT LLM response)
   */
  const handleUserQuery = async (query: string) => {
    setIsLoading(true);
    setError('');

    try {
      // Step 1: Send query to legal RAG backend
      const response = await fetch('/api/v1/ask', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: query,
          chat_history: chatHistory,
        }),
      });

      if (!response.ok) {
        throw new Error(`Backend error: ${response.status}`);
      }

      const data: RAGResponse = await response.json();

      // Step 2: Verify response is "ready_for_llm" (generated prompt, no LLM call)
      if (data.status !== 'ready_for_llm') {
        throw new Error(`Unexpected response status: ${data.status}`);
      }

      // Step 3: Track cache hit for UI display and store retrievals
      setCacheHit(data.metadata.cache_hit);
      setRetrievals(data.retrievals || []);
      setSelectedRetrievalIdx(0);

      // Step 4: Run LLM generation (frontend responsibility)
      const answer = await generateWithLLM(data.prompt, data.retrievals);

      // Step 5: Update chat history
      const newChatHistory: MessageRole[] = [
        ...chatHistory,
        { role: 'user', content: query },
        { role: 'assistant', content: answer }
      ];
      setChatHistory(newChatHistory);

      return answer;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      console.error('Query error:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    try {
      const dismissed = localStorage.getItem('phase20_modal_dismissed');
      if (!dismissed) setShowModal(true);
    } catch (e) {
      // ignore localStorage errors
    }
  }, []);

  /**
   * Phase 2: Send prompt to external LLM (e.g., OpenAI, Gemini)
   *
   * This is the frontend's responsibility when ENABLE_LLM_GENERATION=false
   */
  const generateWithLLM = async (prompt: string, retrievals: Retrieval[]): Promise<string> => {
    // Example: Call OpenAI API
    // const apiKey = process.env.NEXT_PUBLIC_OPENAI_API_KEY;

    // For demo, we'll show both OpenAI and Gemini examples

    // EXAMPLE 1: Using OpenAI
    // const response = await fetch('https://api.openai.com/v1/chat/completions', {
    //   method: 'POST',
    //   headers: {
    //     'Authorization': `Bearer ${apiKey}`,
    //     'Content-Type': 'application/json',
    //   },
    //   body: JSON.stringify({
    //     model: 'gpt-4',
    //     messages: [
    //       {
    //         role: 'system',
    //         content: 'You are a Vietnamese legal expert. Answer questions based on provided legal documents.'
    //       },
    //       {
    //         role: 'user',
    //         content: prompt
    //       }
    //     ],
    //     temperature: 0.7,
    //     max_tokens: 1000,
    //   }),
    // });
    // const result = await response.json();
    // return result.choices[0].message.content;

    // EXAMPLE 2: Using Google Gemini API
    try {
      const geminiApiKey = process.env.NEXT_PUBLIC_GEMINI_API_KEY;
      if (!geminiApiKey) {
        throw new Error('NEXT_PUBLIC_GEMINI_API_KEY not configured');
      }

      const response = await fetch('https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=' + geminiApiKey,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            contents: [
              {
                parts: [
                  {
                    text: prompt
                  }
                ]
              }
            ],
            generationConfig: {
              temperature: 0.7,
              maxOutputTokens: 1000,
            }
          }),
        }
      );

      const result = await response.json();

      if (result.candidates && result.candidates[0]?.content?.parts?.[0]?.text) {
        return result.candidates[0].content.parts[0].text;
      }

      throw new Error('Invalid Gemini response');
    } catch (err) {
      console.error('LLM generation error:', err);
      return `Error generating response: ${err instanceof Error ? err.message : 'Unknown error'}`;
    }
  };

  /**
   * Build a user-facing prompt that can be copied into external chat UIs.
   * This includes a short system instruction in Vietnamese, the original query and
   * a short list of citations/snippets.
   */
  const buildExternalPrompt = (query: string, retrievalsList: Retrieval[]) => {
    const system = `Bạn là một trợ lý pháp lý. Hãy trả lời ngắn gọn, chính xác, và chỉ dựa trên các trích dẫn pháp luật được cung cấp. Nếu cần, trích dẫn nguồn (số hiệu văn bản hoặc tiêu đề).`;

    const snippets = retrievalsList.slice(0, 5).map((r, i) => `Nguồn ${i + 1}: ${r.source}\n"${r.text.replace(/\n/g, ' ')}"`).join('\n\n');

    const prompt = `${system}\n\nYêu cầu: ${query}\n\nTài liệu tham khảo:\n${snippets}\n\nTrả lời (tiếng Việt):`;
    return prompt;
  };

  /**
   * Copy prompt to clipboard and open external chat in a new tab.
   * Note: Browsers do not allow injecting text into another origin's page DOM.
   * We copy the prepared prompt to clipboard and open the external chat URL so
   * the user can simply paste (Ctrl+V) and press Enter.
   */
  const handleCopyAndOpen = async (service: 'chatgpt' | 'gemini') => {
    try {
      const promptText = buildExternalPrompt(chatHistory[chatHistory.length - 1]?.content || '', retrievals);
      await navigator.clipboard.writeText(promptText);

      const url = service === 'chatgpt' ? 'https://chat.openai.com/' : 'https://gemini.google.com/';
      // Open in new tab
      window.open(url, '_blank', 'noopener');

      setCopiedNotice(`Đã sao chép prompt. Trang ${service === 'chatgpt' ? 'ChatGPT' : 'Gemini'} sẽ mở trong tab mới. Nhấn Ctrl+V (hoặc dán) và Enter để gửi.`);
      setTimeout(() => setCopiedNotice(null), 8000);
    } catch (err) {
      console.error('Copy failed', err);
      setCopiedNotice('Không thể sao chép prompt tự động. Vui lòng sao chép thủ công.');
      setTimeout(() => setCopiedNotice(null), 5000);
    }
  };

  /**
   * UI Component for chat interface
   */
  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-blue-600 text-white p-4">
        <h1 className="text-2xl font-bold">Hỏi Đáp Pháp Luật Việt Nam</h1>
        <p className="text-sm mt-1">Vietnamese Legal Q&A System (Phase 19 - Redis Cache)</p>
        <div className="mt-2 flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowModal(true)}
            title="Hướng dẫn: Mở chat ngoài và dán prompt"
            className="bg-white/10 hover:bg-white/20 text-white rounded px-2 py-1 text-xs"
          >
            ? Hướng dẫn
          </button>
          <div className="text-xs text-white/80">Nhấn nút ChatGPT hoặc Gemini để sao chép prompt và mở trang chat.</div>
        </div>
        {cacheHit && (
          <p className="text-green-200 text-sm mt-2 font-semibold">
            ⚡ Cache hit! Faster retrieval from Redis.
          </p>
        )}
      </div>

      {/* Chat Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {chatHistory.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-500">
            <p>Hãy đặt câu hỏi pháp lý của bạn...</p>
          </div>
        ) : (
          chatHistory.map((msg, idx) => (
            <div
              key={idx}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-xl rounded-lg p-3 ${
                  msg.role === 'user'
                    ? 'bg-blue-500 text-white'
                    : 'bg-gray-200 text-gray-800'
                }`}
              >
                <p className="text-sm">{msg.content}</p>
              </div>
            </div>
          ))
        )}

        {isLoading && (
          <div className="flex justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        )}

        {error && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
            Lỗi: {error}
          </div>
        )}
      </div>

      {/* Retrievals Display (Optional) */}
      {showRetrievals && retrievals.length > 0 && (
        <div className="bg-gray-100 p-4 max-h-56 overflow-y-auto">
          <h3 className="font-bold text-sm mb-2">Tài liệu liên quan:</h3>
          <div className="space-y-2">
            {retrievals.map((r, idx) => (
              <div
                key={idx}
                onClick={() => setSelectedRetrievalIdx(idx)}
                className={`p-2 rounded cursor-pointer ${selectedRetrievalIdx === idx ? 'bg-blue-50 border-l-4 border-blue-400' : 'bg-white border'}`}
              >
                <div className="flex justify-between items-center">
                  <div className="text-xs font-semibold">{r.source}</div>
                  <div className="text-xs text-gray-500">score: {r.score.toFixed(2)}</div>
                </div>
                <p className="text-sm text-gray-700 mt-1 truncate">{r.text}</p>
              </div>
            ))}
          </div>

          {/* Preview + External Chat Buttons */}
          <div className="mt-3 border-t pt-3">
            <h4 className="font-medium text-sm mb-1">Xem trước trích đoạn</h4>
            <div className="bg-white p-3 border rounded mb-2">
              <p className="text-sm text-gray-800">{retrievals[selectedRetrievalIdx]?.text}</p>
              <p className="text-xs text-gray-500 mt-2">Nguồn: {retrievals[selectedRetrievalIdx]?.source}</p>
            </div>

            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => handleCopyAndOpen('chatgpt')}
                className="bg-indigo-600 hover:bg-indigo-700 text-white rounded px-3 py-2 text-sm"
              >
                Mở ChatGPT (sao chép prompt)
              </button>
              <button
                type="button"
                onClick={() => handleCopyAndOpen('gemini')}
                className="bg-gray-700 hover:bg-gray-800 text-white rounded px-3 py-2 text-sm"
              >
                Mở Gemini (sao chép prompt)
              </button>
              <button
                type="button"
                onClick={async () => {
                  const promptText = buildExternalPrompt(chatHistory[chatHistory.length - 1]?.content || '', retrievals);
                  try {
                    await navigator.clipboard.writeText(promptText);
                    setCopiedNotice('Đã sao chép prompt vào clipboard.');
                    setTimeout(() => setCopiedNotice(null), 3000);
                  } catch {
                    setCopiedNotice('Không thể sao chép tự động. Vui lòng sao chép thủ công.');
                    setTimeout(() => setCopiedNotice(null), 3000);
                  }
                }}
                className="bg-gray-400 hover:bg-gray-500 text-white rounded px-3 py-2 text-sm"
              >
                Chỉ sao chép prompt
              </button>
            </div>
            {copiedNotice && (
              <div className="mt-2 text-sm text-green-700">{copiedNotice}</div>
            )}
          </div>
        </div>
      )}

      {/* Input Area */}
      {/* Modal: Quick UX guide */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black opacity-40" onClick={() => setShowModal(false)} />
          <div className="relative bg-white rounded-lg max-w-xl w-[90%] p-6 shadow-lg z-10">
            <h3 className="text-lg font-semibold mb-2">Hướng dẫn: Mở ChatGPT / Gemini với prompt đã chuẩn bị</h3>
            <ol className="list-decimal list-inside space-y-2 text-sm text-gray-700">
              <li>Nhấn một trong các nút "Mở ChatGPT" hoặc "Mở Gemini" — hệ thống sẽ sao chép prompt vào clipboard và mở trang chat trong tab mới.</li>
              <li>Chuyển sang tab ChatGPT/Gemini, dán nội dung (Ctrl+V hoặc dán) vào ô chat, sau đó nhấn Enter để gửi.</li>
              <li>Nếu dùng điện thoại: chạm và giữ ô chat > Dán > Gửi.</li>
            </ol>
            <div className="mt-4 flex items-center justify-between">
              <label className="flex items-center gap-2 text-sm text-gray-600">
                <input
                  type="checkbox"
                  checked={dontShowAgain}
                  onChange={(e) => setDontShowAgain(e.target.checked)}
                />
                Không hiển thị lại
              </label>
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    if (dontShowAgain) {
                      try { localStorage.setItem('phase20_modal_dismissed', '1'); } catch {}
                    }
                    setShowModal(false);
                  }}
                  className="bg-blue-600 text-white px-3 py-1 rounded"
                >
                  Đóng
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      <div className="border-t bg-white p-4">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (userQuery.trim()) {
              handleUserQuery(userQuery);
              setUserQuery('');
            }
          }}
          className="flex gap-2"
        >
          <input
            type="text"
            value={userQuery}
            onChange={(e) => setUserQuery(e.target.value)}
            placeholder="Nhập câu hỏi pháp lý của bạn..."
            disabled={isLoading}
            className="flex-1 rounded-lg border border-gray-300 px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            type="submit"
            disabled={isLoading || !userQuery.trim()}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white rounded-lg px-6 py-2 font-medium"
          >
            {isLoading ? 'Đang tìm kiếm...' : 'Gửi'}
          </button>
          <button
            type="button"
            onClick={() => setShowRetrievals(!showRetrievals)}
            className="bg-gray-400 hover:bg-gray-500 text-white rounded-lg px-4 py-2 text-sm"
          >
            {showRetrievals ? 'Ẩn' : 'Hiển thị'} Tài liệu
          </button>
        </form>
        <p className="text-xs text-gray-500 mt-2">
          💡 Tip: Backend trả về tài liệu liên quan (via Redis cache hoặc Qdrant).
          Frontend gửi prompt tới LLM do người dùng chọn.
        </p>
      </div>
    </div>
  );
};

export default LegalRAGChat;

