// App.jsx - Yeni İki Aşamalı Sistem: Plan + Execution

import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './App.css';
import sendIcon from './assets/send.svg';
import fbLogo from './assets/fb-logo.png';
import html2pdf from 'html2pdf.js';
import downloadIcon from './assets/download.svg';

// ProgressIndicator bileşeni güncellendi
const ProgressIndicator = ({ stage, progress, message }) => {
  const STAGES = ['Başlangıç', 'Plan Üretimi', 'Plan Onayı', 'Araştırma', 'Analiz & Yazım', 'Tamamlandı'];
  const stageOrder = { init: 0, generate: 1, approval: 2, research: 3, analyze: 4, completed: 5 };
  const activeIndex = stageOrder[stage] ?? 0;

  return (
    <div className="progress-container">
      <div className="stepper">
        {STAGES.map((label, i) => {
          const status = i < activeIndex ? 'done' : i === activeIndex ? 'active' : 'pending';
          return (
            <div key={label} className={`stepper-item ${status}`} aria-current={i === activeIndex ? 'step' : undefined}>
              <div className="stepper-circle" />
              <div className="stepper-label">{label}</div>
            </div>
          );
        })}
      </div>
      <div className="progress-message">{message}</div>
    </div>
  );
};

// Tek bir dokümanı baloncuk olarak gösteren bileşen
const DocumentBubble = ({ filename, content }) => {
  const contentRef = useRef(null);

  const handleDownload = () => {
    if (!contentRef.current) return;
    const fileBase = (filename || 'document').replace(/\s+/g, '_');
    const opt = {
      margin: [10, 12, 10, 12],
      filename: `${fileBase.replace(/\.[^.]+$/, '')}.pdf`,
      image: { type: 'jpeg', quality: 0.98 },
      html2canvas: { scale: 2, useCORS: true },
      jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' }
    };
    html2pdf().from(contentRef.current).set(opt).save();
  };

  return (
    <div className="message agent">
      <button type="button" className="download-button" onClick={handleDownload} aria-label="PDF indir">
        <img src={downloadIcon} alt="İndir" className="download-icon" />
      </button>
      <div className="doc-content" ref={contentRef}>
        <div className="doc-title">{filename}</div>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>
    </div>
  );
};

// Plan Editor - Step-by-step görsel akış tasarımı
const PlanEditor = ({ plan, onConfirm, onCancel, isReadonly = false }) => {
  const defaultFiles = ['pain_points.md', 'roadmap.md', 'business_strategy.md'];
  const inferFilesFromPlan = () => {
    if (Array.isArray(plan?.output_files) && plan.output_files.length > 0) {
      return plan.output_files;
    }
    if (typeof plan?.output_format === 'string' && plan.output_format.trim()) {
      return plan.output_format
        .split('\n')
        .map(s => (s || '').trim())
        .filter(Boolean);
    }
    return defaultFiles;
  };

  const [editedPlan, setEditedPlan] = useState({
    research_queries: plan?.research_queries || [],
    analysis_focus: plan?.analysis_focus || [],
    output_files: inferFilesFromPlan()
  });

  const handleQueriesChange = (queries) => {
    setEditedPlan(prev => ({ ...prev, research_queries: queries }));
  };

  const handleAnalysisChange = (focuses) => {
    setEditedPlan(prev => ({ ...prev, analysis_focus: focuses }));
  };

  const updateOutputFile = (index, value) => {
    const files = [...(editedPlan.output_files || [])];
    files[index] = value;
    setEditedPlan(prev => ({ ...prev, output_files: files }));
  };

  const removeOutputFile = (index) => {
    const files = (editedPlan.output_files || []).filter((_, i) => i !== index);
    setEditedPlan(prev => ({ ...prev, output_files: files }));
  };

  const addOutputFile = () => {
    const files = editedPlan.output_files || [];
    if (files.length >= 3) return; // en fazla 3 dosya
    setEditedPlan(prev => ({ ...prev, output_files: [...files, ''] }));
  };

  const handleConfirm = () => {
    const files = (editedPlan.output_files || [])
      .map(f => (f || '').trim())
      .filter(Boolean);
    const normalizedFiles = (files.length ? files : defaultFiles).slice(0, 3);
    onConfirm({
      ...editedPlan,
      output_files: normalizedFiles,
      output_format: normalizedFiles.join('\n')
    });
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
          <div className="step-connector"></div>
          <div className="step-editor">
            <div className="output-info">
              <div className="output-item">
                <label>Format:</label>
                {isReadonly ? (
                  <div className="fixed-format-display">
                    {(editedPlan.output_files || defaultFiles).map((line, idx) => (
                      <div key={idx}><span>{line}</span></div>
                    ))}
                  </div>
                ) : (
                  <div className="analysis-list">
                    {(editedPlan.output_files || []).map((file, idx) => (
                      <div key={idx} className="analysis-item">
                        <input
                          type="text"
                          className="output-input"
                          value={file}
                          onChange={(e) => updateOutputFile(idx, e.target.value)}
                          placeholder={defaultFiles[idx] || 'dosya.md'}
                        />
                        <button 
                          className="remove-btn"
                          onClick={() => removeOutputFile(idx)}
                          type="button"
                        >
                          ×
                        </button>
                      </div>
                    ))}
                    {editedPlan.output_files.length < 3 && (
                      <button className="add-btn" onClick={addOutputFile} type="button">
                        + Yeni Dosya Ekle
                      </button>
                    )}
                  </div>
                )}
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

  const showWelcome = messages.length === 0 && planEditorState === 'hidden' && !isLoading;
  const welcomeInputRef = useRef(null);

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
        // Normalize analysis_focus to exactly 3 items for initial render
        const rawFocus = Array.isArray(data?.plan?.analysis_focus) ? data.plan.analysis_focus : [];
        const normalizedFocus = Array.from(new Set(rawFocus.map(f => (f || '').trim()).filter(f => f))).slice(0, 3);
        const paddedFocus = normalizedFocus.concat(Array(Math.max(0, 3 - normalizedFocus.length)).fill(''));
        const normalizedPlan = { ...data.plan, analysis_focus: paddedFocus };

        setPendingPlan(normalizedPlan);
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

    const rawFormat = typeof confirmedPlan?.output_format === 'string'
      ? confirmedPlan.output_format
      : Array.isArray(confirmedPlan?.output_files)
        ? confirmedPlan.output_files.join('\n')
        : '';
    const sanitizedFiles = rawFormat.split('\n').map(s => (s || '').trim()).filter(Boolean);
    const normalizedFormat = sanitizedFiles.join('\n') || 'pain_points.md\nroadmap.md\nbusiness_strategy.md';

    const sanitizedPlan = {
      research_queries: limitedQueries,
      analysis_focus: sanitizedFocus,
      output_format: normalizedFormat
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
          const docs = Array.isArray(data?.documents) ? data.documents : [];
          if (docs.length > 0) {
            setMessages(prev => [
              ...prev,
              ...docs.map(d => ({ sender: 'agent', isComplete: true, isDocument: true, filename: d.filename, text: d.content }))
            ]);
          } else {
            const agentMessage = { text: data.result, sender: 'agent', isComplete: true };
            setMessages(prev => [...prev, agentMessage]);
          }
          setCurrentStage({ stage: 'completed', progress: 100, message: 'İş analizi başarıyla tamamlandı!' });
          setIsLoading(false);
        }, 1000);
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

  // Kullanıcı mesajlarının genişliğini uzunluğa göre dinamik ayarla
  const computeUserMessageMaxWidth = (text) => {
    const normalizedLength = (text || '').replace(/\s+/g, ' ').trim().length;
    if (normalizedLength <= 40) return '70%';
    if (normalizedLength <= 120) return '60%';
    if (normalizedLength <= 240) return '50%';
    return '45%';
  };

  return (
    <div className="app-container">
      <div className={`sidebar ${isSidebarOpen ? 'open' : ''}`}>
         <div className="sidebar-header">
           <h3>Proje Aşamaları</h3>
         </div>
         <div className="sidebar-content">
          <ul className="stages-flow">
            <li className="stage-item active" aria-current="step">İhtiyaç Analizi</li>
            <li className="stage-item passive" aria-disabled="true">Kod Gelişimi</li>
            <li className="stage-item passive" aria-disabled="true">Test</li>
            <li className="stage-item passive" aria-disabled="true">Deployment</li>
          </ul>
        </div>
      </div>

      {/* Sidebar açıkken görünen arkaplan - tıklanınca kapatır */}
      <div
        className={`backdrop ${isSidebarOpen ? 'visible' : ''}`}
        onClick={() => setIsSidebarOpen(false)}
      />

      <div className="chat-container">
        <div className="header">
          <div className="header-left">
            <button className="hamburger-button" onClick={toggleSidebar} aria-expanded={isSidebarOpen} aria-label="Menüyü aç/kapat">
              <div className="hamburger-icon"><span></span><span></span><span></span></div>
            </button>
          </div>
          <div className="header-right">
            <img src={fbLogo} alt="FibaBanka" className="header-logo" />
          </div>
        </div>

        <div className="main-container">
          {showWelcome ? (
            <div className="welcome-container">
              <img src={fbLogo} alt="FibaBanka" className="welcome-logo" />
              <h1 className="welcome-title">İhtiyaç Analizi Asistanı'na Hoş Geldiniz!</h1>
              <p className="welcome-description">
                    Proje fikrinizin ana hatlarını paylaşın; pazar potansiyelini, hedef kitleyi ve temel gereksinimleri sizin için analiz edip özetleyeyim.
              </p>
              <div className="suggestion-buttons">
                <button
                  type="button"
                  className="suggestion-button"
                  onClick={() => { setInput("KOBİ'ler için QR kod ile ödeme altyapısı"); welcomeInputRef.current?.focus(); }}
                >
                  KOBİ'ler için QR kod ile ödeme altyapısı
                </button>
                <button
                  type="button"
                  className="suggestion-button"
                  onClick={() => { setInput('Mobil uygulama kullanıcılarımızın daha aktif olması için kampanya önerileri'); welcomeInputRef.current?.focus(); }}
                >
                  Mobil uygulama kullanıcılarımızın daha aktif olması için kampanya önerileri
                </button>
              </div>
              <div className="input-row">
                <input
                  ref={welcomeInputRef}
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
                  placeholder="Buraya proje bilgilerinizi giriniz."
                  disabled={isLoading || planEditorState === 'editing'}
                />
                <button 
                  onClick={sendMessage} 
                  disabled={isLoading || planEditorState === 'editing'}
                  className="send-button"
                  aria-label="Gönder"
                >
                  <img src={sendIcon} alt="Send" className="send-icon" />
                </button>
              </div>
            </div>
          ) : (
            <>
              <div className="messages">
                {messages.map((msg, index) => {
                  const lastUserMessageIndex = messages.map(m => m.sender).lastIndexOf('user');
                  const isLastUserMessage = msg.sender === 'user' && index === lastUserMessageIndex;
                  if (msg.isDocument) {
                    return (
                      <React.Fragment key={index}>
                        <DocumentBubble filename={msg.filename} content={msg.text} />
                        {isLastUserMessage && planEditorState === 'approved' && (
                          <PlanEditor
                            plan={approvedPlan}
                            onConfirm={() => {}}
                            onCancel={() => {}}
                            isReadonly={true}
                          />
                        )}
                      </React.Fragment>
                    );
                  }
                  return (
                    <React.Fragment key={index}>
                      <div className={`message ${msg.sender}`}>
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.text}</ReactMarkdown>
                      </div>
                      {isLastUserMessage && planEditorState === 'approved' && (
                        <PlanEditor
                          plan={approvedPlan}
                          onConfirm={() => {}}
                          onCancel={() => {}}
                          isReadonly={true}
                        />
                      )}
                    </React.Fragment>
                  );
                })}
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
                <div className="input-row">
                  <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
                    placeholder="Buraya proje bilgilerinizi giriniz."
                    disabled={isLoading || planEditorState === 'editing'}
                  />
                  <button 
                    onClick={sendMessage} 
                    disabled={isLoading || planEditorState === 'editing'}
                    className="send-button"
                    aria-label="Gönder"
                  >
                    <img src={sendIcon} alt="Send" className="send-icon" />
                  </button>
                </div>
                {isLoading && (
                  <ProgressIndicator 
                    stage={currentStage.stage}
                    progress={currentStage.progress}
                    message={currentStage.message}
                  />
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;