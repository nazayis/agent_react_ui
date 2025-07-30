// App.jsx - Yeni 3-Aşamalı Endpoint Versiyonu

import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './App.css';

// ProgressIndicator bileşeni güncellendi
const ProgressIndicator = ({ stage, progress, message }) => {
  return (
    <div className="progress-container">
      <div className="progress-bar-container">
        <div className="progress-bar-fill" style={{ width: `${progress}%` }}/>
      </div>
      <div className="progress-stages">
        <div className={`stage ${progress >= 0 ? 'active' : ''}`}>Başlangıç</div>
        <div className={`stage ${progress >= 25 ? 'active' : ''}`}>Sorgu Üretimi</div>
        <div className={`stage ${progress >= 40 ? 'active' : ''}`}>Onay</div>
        <div className={`stage ${progress >= 60 ? 'active' : ''}`}>Araştırma</div>
        <div className={`stage ${progress >= 80 ? 'active' : ''}`}>Analiz & Yazım</div>
        <div className={`stage ${progress >= 100 ? 'active' : ''}`}>Tamamlandı</div>
      </div>
      <div className="progress-message">{message}</div>
    </div>
  );
};

// Gömülü Query Editor - Hem editable hem readonly modda çalışıyor
const EmbeddedQueryEditor = ({ queries, onConfirm, onCancel, isReadonly = false }) => {
  const [editedText, setEditedText] = useState(
    () => queries.map(q => q.query).join('\n')
  );

  const handleConfirm = () => {
    const newQueryStrings = editedText.split('\n').filter(q => q.trim() !== '');
    const confirmedQueries = newQueryStrings.map((queryString, index) => ({
      query: queryString,
      field_name: queries[index] ? queries[index].field_name : `query_${index + 1}`,
      approved: true,
    }));
    onConfirm(confirmedQueries);
  };

  return (
    <div className={`embedded-editor-container ${isReadonly ? 'readonly' : ''}`}>
      <div className="editor-header">
        <h3>{isReadonly ? 'Onaylanan Arama Sorguları' : 'Arama Sorgularını Onaylayın'}</h3>
        {!isReadonly && (
          <p>Ajan aşağıdaki sorguları kullanmayı öneriyor. Üzerinde değişiklik yapabilir, silebilir veya yeni sorgular ekleyebilirsiniz. (Her sorgu ayrı bir satırda olmalıdır.)</p>
        )}
        {isReadonly && (
          <p>Bu sorgular ile araştırma yapılıyor:</p>
        )}
      </div>
      <textarea
        className={`query-textarea ${isReadonly ? 'readonly' : ''}`}
        value={editedText}
        onChange={isReadonly ? undefined : (e) => setEditedText(e.target.value)}
        disabled={isReadonly}
        rows={10}
      />
      {!isReadonly && (
        <div className="editor-footer">
          <button onClick={onCancel} className="btn-cancel">İptal</button>
          <button onClick={handleConfirm} className="btn-confirm">Onayla ve Devam Et</button>
        </div>
      )}
    </div>
  );
};

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  // State yönetimi
  const [queryEditorState, setQueryEditorState] = useState('hidden'); // 'hidden', 'editing', 'approved'
  const [pendingQueries, setPendingQueries] = useState([]);
  const [approvedQueries, setApprovedQueries] = useState([]);
  const [currentRunId, setCurrentRunId] = useState(null);
  
  const [currentStage, setCurrentStage] = useState({ stage: 'init', progress: 0, message: 'Hazırlanıyor...' });
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, queryEditorState]);

  const handleApiError = (error, context) => {
    console.error(`API Hatası (${context}):`, error);
    setMessages(prev => [...prev, { 
      text: `Hata oluştu (${context}): ${error.message}`, 
      sender: 'agent', 
      isComplete: true 
    }]);
    setIsLoading(false);
    setCurrentStage({ stage: 'error', progress: 0, message: 'Hata oluştu.' });
  };

  // YENİ: 1. Aşama - Sorgu üretimi
  const sendMessage = async () => {
    if (input.trim() === '' || isLoading) return;

    const userMessage = { text: input, sender: 'user', isComplete: true };
    setMessages(prev => [...prev, userMessage]); 
    const currentInput = input;
    setInput('');
    setIsLoading(true);
    setQueryEditorState('hidden');
    setApprovedQueries([]);
    setCurrentStage({ stage: 'generate', progress: 25, message: 'Arama sorguları üretiliyor...' });

    try {
      const response = await fetch('http://localhost:5001/generate-queries', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: currentInput }),
      });
      const data = await response.json();
      
      if (response.ok) {
        if (data.is_paused && data.queries && data.queries.length > 0) {
          setPendingQueries(data.queries);
          setCurrentRunId(data.run_id);
          setQueryEditorState('editing');
          setCurrentStage({ stage: 'approval', progress: 40, message: 'Sorgular onayınızı bekliyor...' });
          setIsLoading(false);
        } else {
          throw new Error('Beklenmeyen yanıt formatı');
        }
      } else {
        throw new Error(data.error || 'Sorgu üretimi sırasında hata oluştu');
      }
    } catch (error) {
      handleApiError(error, 'sorgu üretimi');
    }
  };

  // YENİ: 2. Aşama - Arama yapma
  const handleQueryConfirmation = async (confirmedQueries) => {
    setApprovedQueries(confirmedQueries);
    setQueryEditorState('approved');
    setIsLoading(true);
    setCurrentStage({ stage: 'research', progress: 60, message: 'Onaylanan sorgularla araştırma yapılıyor...' });

    try {
      const response = await fetch('http://localhost:5001/execute-search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          run_id: currentRunId,
          approved_queries: confirmedQueries
        }),
      });
      const data = await response.json();
      
      if (response.ok && data.urls) {
        // 3. Aşamaya geç - Analiz ve teklif yazımı
        await analyzeAndPropose(data.urls);
      } else {
        throw new Error(data.error || 'Arama sırasında hata oluştu');
      }
    } catch (error) {
      handleApiError(error, 'arama işlemi');
    } finally {
      setCurrentRunId(null);
      setPendingQueries([]);
    }
  };

  // YENİ: 3. Aşama - Analiz ve teklif yazımı
  const analyzeAndPropose = async (urls) => {
    setCurrentStage({ stage: 'analyze', progress: 80, message: 'İçerik analiz ediliyor ve teklif yazılıyor...' });

    try {
      const response = await fetch('http://localhost:5001/analyze-and-propose', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ urls: urls }),
      });
      const data = await response.json();
      
      if (response.ok && data.proposal) {
        const agentMessage = { text: data.proposal, sender: 'agent', isComplete: true };
        setMessages(prev => [...prev, agentMessage]);
        setCurrentStage({ stage: 'completed', progress: 100, message: 'İş teklifi başarıyla tamamlandı!' });
        setIsLoading(false);
      } else {
        throw new Error(data.error || 'Analiz ve teklif yazımı sırasında hata oluştu');
      }
    } catch (error) {
      handleApiError(error, 'analiz ve teklif yazımı');
    }
  };
  
  const handleQueryCancel = () => {
    setQueryEditorState('hidden');
    setIsLoading(false);
    setCurrentRunId(null);
    setPendingQueries([]);
    setApprovedQueries([]);
    setMessages(prev => [...prev, { text: 'İşlem kullanıcı tarafından iptal edildi.', sender: 'agent', isComplete: true }]);
    setCurrentStage({ stage: 'init', progress: 0, message: 'İptal edildi.' });
  };

  const toggleSidebar = () => setIsSidebarOpen(!isSidebarOpen);

  return (
    <div className="app-container">
      <button className="hamburger-button" onClick={toggleSidebar}>
        <div className="hamburger-icon"><span></span><span></span><span></span></div>
      </button>

      <div className={`sidebar ${isSidebarOpen ? 'open' : ''}`}>
         {/* Sidebar içeriği */}
      </div>

      <div className="chat-container">
        <div className="header">
          <p>aşağıdaki alana ihtiyaç analiz için isteğini detaylandır</p>
        </div>
        
        <div className="messages">
          {messages.map((msg, index) => (
            <div key={index} className={`message ${msg.sender}`}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.text}</ReactMarkdown>
            </div>
          ))}

          {/* Query Editor - editing veya approved modda gösteriliyor */}
          {queryEditorState === 'editing' && (
            <EmbeddedQueryEditor
              queries={pendingQueries}
              onConfirm={handleQueryConfirmation}
              onCancel={handleQueryCancel}
              isReadonly={false}
            />
          )}
          
          {queryEditorState === 'approved' && (
            <EmbeddedQueryEditor
              queries={approvedQueries}
              onConfirm={() => {}}
              onCancel={() => {}}
              isReadonly={true}
            />
          )}

          <div ref={messagesEndRef} />
        </div>

        <div className="input-area">
          {isLoading && (
            <ProgressIndicator 
              stage={currentStage.stage}
              progress={currentStage.progress}
              message={currentStage.message}
            />
          )}
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
            placeholder="kullanıcı input chat box"
            disabled={isLoading || queryEditorState === 'editing'}
          />
          <button 
            onClick={sendMessage} 
            disabled={isLoading || queryEditorState === 'editing'}
          >
            Gönder
          </button>
        </div>
      </div>
    </div>
  );
}

export default App;