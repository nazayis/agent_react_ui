// App.jsx - Yeni İki Aşamalı Sistem: Plan + Execution

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
        <div className={`stage ${progress >= 25 ? 'active' : ''}`}>Plan Üretimi</div>
        <div className={`stage ${progress >= 40 ? 'active' : ''}`}>Plan Onayı</div>
        <div className={`stage ${progress >= 60 ? 'active' : ''}`}>Araştırma</div>
        <div className={`stage ${progress >= 80 ? 'active' : ''}`}>Analiz & Yazım</div>
        <div className={`stage ${progress >= 100 ? 'active' : ''}`}>Tamamlandı</div>
      </div>
      <div className="progress-message">{message}</div>
    </div>
  );
};

// Plan Editor - Step-by-step görsel akış tasarımı
const PlanEditor = ({ plan, onConfirm, onCancel, isReadonly = false }) => {
  const [editedPlan, setEditedPlan] = useState({
    research_queries: plan?.research_queries || [],
    analysis_focus: plan?.analysis_focus || []
  });

  const handleQueriesChange = (queries) => {
    setEditedPlan(prev => ({ ...prev, research_queries: queries }));
  };

  const handleAnalysisChange = (focuses) => {
    setEditedPlan(prev => ({ ...prev, analysis_focus: focuses }));
  };

  const handleConfirm = () => {
    onConfirm(editedPlan);
  };

  const addQuery = () => {
    setEditedPlan(prev => ({ 
      ...prev, 
      research_queries: [...prev.research_queries, ''] 
    }));
  };

  const updateQuery = (index, value) => {
    const newQueries = [...editedPlan.research_queries];
    newQueries[index] = value;
    handleQueriesChange(newQueries);
  };

  const removeQuery = (index) => {
    const newQueries = editedPlan.research_queries.filter((_, i) => i !== index);
    handleQueriesChange(newQueries);
  };

  const addAnalysis = () => {
    setEditedPlan(prev => ({ 
      ...prev, 
      analysis_focus: [...prev.analysis_focus, ''] 
    }));
  };

  const updateAnalysis = (index, value) => {
    const newFocuses = [...editedPlan.analysis_focus];
    newFocuses[index] = value;
    handleAnalysisChange(newFocuses);
  };

  const removeAnalysis = (index) => {
    const newFocuses = editedPlan.analysis_focus.filter((_, i) => i !== index);
    handleAnalysisChange(newFocuses);
  };

  return (
    <div className={`step-flow-container ${isReadonly ? 'readonly' : ''}`}>
      <div className="step-flow-header">
        <h3>{isReadonly ? 'Onaylanan Çalışma Planı' : 'Çalışma Planını Düzenleyin'}</h3>
        {!isReadonly && (
          <p>Her adımı düzenleyebilirsiniz. Tamamlandığında sistem bu planı otomatik olarak çalıştıracak.</p>
        )}
      </div>

      <div className="step-flow-content">
        {/* Step 1: Araştırma */}
        <div className="step-item">
          <div className="step-box">
            <div className="step-number">1</div>
            <div className="step-title">Araştırma</div>
          </div>
          <div className="step-connector"></div>
          <div className="step-editor">
            <h4>Arama Sorguları</h4>
            <div className="query-list">
              {editedPlan.research_queries.map((query, index) => (
                <div key={index} className="query-item">
                  <input
                    type="text"
                    className={`query-input ${isReadonly ? 'readonly' : ''}`}
                    value={query}
                    onChange={isReadonly ? undefined : (e) => updateQuery(index, e.target.value)}
                    disabled={isReadonly}
                    placeholder={`Arama sorgusu ${index + 1}`}
                  />
                  {!isReadonly && (
                    <button 
                      className="remove-btn"
                      onClick={() => removeQuery(index)}
                      type="button"
                    >
                      ×
                    </button>
                  )}
                </div>
              ))}
              {!isReadonly && (
                <button className="add-btn" onClick={addQuery} type="button">
                  + Yeni Sorgu Ekle
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Step 2: Analiz */}
        <div className="step-item">
          <div className="step-box">
            <div className="step-number">2</div>
            <div className="step-title">Analiz</div>
          </div>
          <div className="step-connector"></div>
          <div className="step-editor">
            <h4>Analiz Odakları</h4>
            <div className="analysis-list">
              {editedPlan.analysis_focus.map((focus, index) => (
                <div key={index} className="analysis-item">
                  <input
                    type="text"
                    className={`analysis-input ${isReadonly ? 'readonly' : ''}`}
                    value={focus}
                    onChange={isReadonly ? undefined : (e) => updateAnalysis(index, e.target.value)}
                    disabled={isReadonly}
                    placeholder={`Analiz odağı ${index + 1}`}
                  />
                  {!isReadonly && (
                    <button 
                      className="remove-btn"
                      onClick={() => removeAnalysis(index)}
                      type="button"
                    >
                      ×
                    </button>
                  )}
                </div>
              ))}
              {!isReadonly && (
                <button className="add-btn" onClick={addAnalysis} type="button">
                  + Yeni Analiz Odağı Ekle
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Step 3: Çıktı */}
        <div className="step-item">
          <div className="step-box">
            <div className="step-number">3</div>
            <div className="step-title">Çıktı</div>
          </div>
          <div className="step-editor">
            <div className="output-info">
              <div className="output-item">
                <label>Format:</label>
                <div className="fixed-format-display">
                  <span>3 dosya: pain_points.md, roadmap.xlsx, business_strategy.md</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {!isReadonly && (
        <div className="step-flow-footer">
          <button onClick={onCancel} className="btn-cancel">İptal</button>
          <button onClick={handleConfirm} className="btn-confirm">Planı Onayla ve Başlat</button>
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
  const [planEditorState, setPlanEditorState] = useState('hidden'); // 'hidden', 'editing', 'approved'
  const [pendingPlan, setPendingPlan] = useState(null);
  const [approvedPlan, setApprovedPlan] = useState(null);
  
  const [currentStage, setCurrentStage] = useState({ stage: 'init', progress: 0, message: 'Hazırlanıyor...' });
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, planEditorState]);

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

  // YENİ: 1. Aşama - Plan üretimi
  const sendMessage = async () => {
    if (input.trim() === '' || isLoading) return;

    const userMessage = { text: input, sender: 'user', isComplete: true };
    setMessages(prev => [...prev, userMessage]); 
    const currentInput = input;
    setInput('');
    setIsLoading(true);
    setPlanEditorState('hidden');
    setApprovedPlan(null);
    setCurrentStage({ stage: 'generate', progress: 25, message: 'Çalışma planı üretiliyor...' });

    try {
      const response = await fetch('http://localhost:5001/generate-plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: currentInput }),
      });
      const data = await response.json();
      
      if (response.ok && data.success) {
        setPendingPlan(data.plan);
        setPlanEditorState('editing');
        setCurrentStage({ stage: 'approval', progress: 40, message: 'Plan onayınızı bekliyor...' });
        setIsLoading(false);
      } else {
        throw new Error(data.error || 'Plan üretimi sırasında hata oluştu');
      }
    } catch (error) {
      handleApiError(error, 'plan üretimi');
    }
  };

  // YENİ: 2. Aşama - Plan çalıştırma
  const handlePlanConfirmation = async (confirmedPlan) => {
    // Sanitize queries: trim, remove empty, de-duplicate, cap to 5
    const sanitizedQueries = Array.from(new Set((confirmedPlan?.research_queries || [])
      .map(q => (q || '').trim())
      .filter(q => q)));
    const limitedQueries = sanitizedQueries.slice(0, 5);

    const sanitizedFocus = (confirmedPlan?.analysis_focus || [])
      .map(f => (f || '').trim())
      .filter(f => f);

    const sanitizedPlan = {
      research_queries: limitedQueries,
      analysis_focus: sanitizedFocus
    };

    setApprovedPlan(sanitizedPlan);
    setPlanEditorState('approved');
    setIsLoading(true);
    setCurrentStage({ stage: 'research', progress: 60, message: 'Plan çalıştırılıyor - araştırma başladı...' });

    try {
      const response = await fetch('http://localhost:5001/execute-plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan: sanitizedPlan }),
      });
      const data = await response.json();
      
      if (response.ok && data.success) {
        setCurrentStage({ stage: 'analyze', progress: 80, message: 'Analiz tamamlanıyor...' });
        
        setTimeout(() => {
          const agentMessage = { text: data.result, sender: 'agent', isComplete: true };
          setMessages(prev => [...prev, agentMessage]);
          setCurrentStage({ stage: 'completed', progress: 100, message: 'İş analizi başarıyla tamamlandı!' });
          setIsLoading(false);
        }, 2000);
      } else {
        throw new Error(data.error || 'Plan çalıştırma sırasında hata oluştu');
      }
    } catch (error) {
      handleApiError(error, 'plan çalıştırma');
    } finally {
      setPendingPlan(null);
    }
  };
  
  const handlePlanCancel = () => {
    setPlanEditorState('hidden');
    setIsLoading(false);
    setPendingPlan(null);
    setApprovedPlan(null);
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
            // Son kullanıcı mesajını bul
            const lastUserMessageIndex = messages.map(m => m.sender).lastIndexOf('user');
            const isLastUserMessage = msg.sender === 'user' && index === lastUserMessageIndex;
            
            return (
              <div key={index}>
                <div className={`message ${msg.sender}`}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.text}</ReactMarkdown>
                </div>
                
                {/* Son kullanıcı mesajından sonra onaylanan planı göster */}
                {isLastUserMessage && planEditorState === 'approved' && (
                  <PlanEditor
                    plan={approvedPlan}
                    onConfirm={() => {}}
                    onCancel={() => {}}
                    isReadonly={true}
                  />
                )}
              </div>
            );
          })}

          {/* Plan Editor - sadece editing modda gösteriliyor */}
          {planEditorState === 'editing' && (
            <PlanEditor
              plan={pendingPlan}
              onConfirm={handlePlanConfirmation}
              onCancel={handlePlanCancel}
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
            disabled={isLoading || planEditorState === 'editing'}
          />
          <button 
            onClick={sendMessage} 
            disabled={isLoading || planEditorState === 'editing'}
          >
            Gönder
          </button>
        </div>
      </div>
    </div>
  );
}

export default App;