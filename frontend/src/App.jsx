// App.jsx - User Control Flows ile Entegre Versiyon

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
        <div className={`stage ${progress >= 15 ? 'active' : ''}`}>Araştırma</div>
        <div className={`stage ${progress >= 25 ? 'active' : ''}`}>Onay</div>
        <div className={`stage ${progress >= 50 ? 'active' : ''}`}>Analiz</div>
        <div className={`stage ${progress >= 75 ? 'active' : ''}`}>Yazım</div>
        <div className={`stage ${progress >= 100 ? 'active' : ''}`}>Tamamlandı</div>
      </div>
      <div className="progress-message">{message}</div>
    </div>
  );
};

// Query Editor - User Control Flows için
const QueryEditor = ({ queries, onConfirm, onCancel, isReadonly = false }) => {
  const [editedQueries, setEditedQueries] = useState(
    () => queries.map(q => ({ ...q, query: q.query || '', approved: true }))
  );

  const handleQueryChange = (index, newQuery) => {
    setEditedQueries(prev => 
      prev.map((q, i) => i === index ? { ...q, query: newQuery } : q)
    );
  };

  const handleConfirm = () => {
    const confirmedQueries = editedQueries.filter(q => q.query.trim() !== '');
    onConfirm(confirmedQueries);
  };

  return (
    <div className={`embedded-editor-container ${isReadonly ? 'readonly' : ''}`}>
      <div className="editor-header">
        <h3>{isReadonly ? 'Onaylanan Arama Sorguları' : 'Arama Sorgularını Onaylayın'}</h3>
        {!isReadonly && (
          <p>Ajan aşağıdaki sorguları öneriyor. İstediğiniz değişiklikleri yapabilirsiniz:</p>
        )}
        {isReadonly && (
          <p>Bu sorgular ile araştırma yapıldı:</p>
        )}
      </div>
      
      <div className="queries-list">
        {editedQueries.map((query, index) => (
          <div key={index} className="query-item">
            <label>Sorgu {index + 1}:</label>
            <input
              type="text"
              value={query.query}
              onChange={isReadonly ? undefined : (e) => handleQueryChange(index, e.target.value)}
              disabled={isReadonly}
              className={`query-input ${isReadonly ? 'readonly' : ''}`}
            />
          </div>
        ))}
      </div>
      
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
    setQueryEditorState('hidden');
    setCurrentRunId(null);
    setPendingQueries([]);
  };

  // Ana mesaj gönderme işlemi - /chat endpoint'ini kullanır
  const sendMessage = async () => {
    if (input.trim() === '' || isLoading) return;

    const userMessage = { text: input, sender: 'user', isComplete: true };
    setMessages(prev => [...prev, userMessage]); 
    const currentInput = input;
    setInput('');
    setIsLoading(true);
    setQueryEditorState('hidden');
    setApprovedQueries([]);
    setCurrentStage({ stage: 'init', progress: 0, message: 'İşlem başlatılıyor...' });

    try {
      const response = await fetch('http://localhost:5001/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          message: currentInput,
          user_id: 'business-proposer-demo',
          session_id: new Date().getTime().toString()
        }),
      });
      const data = await response.json();
      
      // DEBUG: Backend response'unu console'a log et
      console.log('Backend Response:', data);
      
      if (response.ok) {
        // Backend'ten gelen stage bilgilerini güncelle
        if (data.stage && data.progress !== undefined) {
          setCurrentStage({
            stage: data.stage,
            progress: data.progress,
            message: data.message || 'İşleniyor...'
          });
        }

        if (data.is_paused && data.queries && data.queries.length > 0) {
          // User control flow - kullanıcı onayı gerekiyor
          console.log('Queries found:', data.queries);
          setPendingQueries(data.queries);
          setCurrentRunId(data.run_id);
          setQueryEditorState('editing');
          setIsLoading(false);
        } else if (data.response) {
          // İşlem tamamlandı
          const agentMessage = { text: data.response, sender: 'agent', isComplete: true };
          setMessages(prev => [...prev, agentMessage]);
          setIsLoading(false);
        } else {
          console.log('Unexpected response format - data:', data);
          throw new Error('Beklenmeyen yanıt formatı');
        }
      } else {
        throw new Error(data.error || 'Bilinmeyen hata oluştu');
      }
    } catch (error) {
      handleApiError(error, 'mesaj gönderimi');
    }
  };

  // Query onaylama ve devam etme - /resume endpoint'ini kullanır
  const handleQueryConfirmation = async (confirmedQueries) => {
    setApprovedQueries(confirmedQueries);
    setQueryEditorState('hidden');
    
    // Onaylanan sorguları mesaj olarak ekle
    const approvedQueriesMessage = {
      text: '',
      sender: 'queries',
      isComplete: true,
      queries: confirmedQueries
    };
    setMessages(prev => [...prev, approvedQueriesMessage]);
    
    setIsLoading(true);
    setCurrentStage({ stage: 'research', progress: 30, message: 'Onaylanan sorgularla araştırma yapılıyor...' });

    try {
      const response = await fetch('http://localhost:5001/resume', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          run_id: currentRunId,
          approved_queries: confirmedQueries
        }),
      });
      const data = await response.json();
      
      if (response.ok) {
        // Backend'ten gelen stage bilgilerini güncelle
        if (data.stage && data.progress !== undefined) {
          setCurrentStage({
            stage: data.stage,
            progress: data.progress,
            message: data.message || 'İşleniyor...'
          });
        }

        if (data.response) {
          // İşlem tamamlandı
          const agentMessage = { text: data.response, sender: 'agent', isComplete: true };
          setMessages(prev => [...prev, agentMessage]);
          setIsLoading(false);
        } else if (data.is_paused) {
          // Hala başka bir onay bekleniyor (olası ama beklenmez)
          setCurrentRunId(data.run_id);
          setIsLoading(false);
        } else {
          throw new Error('Beklenmeyen yanıt formatı');
        }
      } else {
        throw new Error(data.error || 'Devam etme sırasında hata oluştu');
      }
    } catch (error) {
      handleApiError(error, 'sorgu onaylama');
    } finally {
      setCurrentRunId(null);
      setPendingQueries([]);
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
          {messages.map((msg, index) => {
            if (msg.sender === 'queries') {
              // Onaylanan sorguları özel component olarak render et
              return (
                <div key={index}>
                  <QueryEditor
                    queries={msg.queries}
                    onConfirm={() => {}}
                    onCancel={() => {}}
                    isReadonly={true}
                  />
                </div>
              );
            }
            
            // Normal mesajları render et
            return (
              <div key={index} className={`message ${msg.sender}`}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.text}</ReactMarkdown>
              </div>
            );
          })}

          {/* Query Editor - sadece editing modda gösteriliyor */}
          {queryEditorState === 'editing' && (
            <QueryEditor
              queries={pendingQueries}
              onConfirm={handleQueryConfirmation}
              onCancel={handleQueryCancel}
              isReadonly={false}
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