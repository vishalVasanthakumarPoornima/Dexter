import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type DependencyList,
  type ReactNode,
} from "react";
import {
  BriefcaseBusiness,
  Bot,
  Calendar,
  CheckCircle2,
  Code2,
  FileText,
  Files,
  FolderSearch,
  Gauge,
  GitBranch,
  History,
  LayoutDashboard,
  List,
  MemoryStick,
  Mic,
  Send,
  Settings,
  Shield,
  Square,
  Terminal,
  Upload,
  Wrench,
} from "lucide-react";
import {
  auditTools,
  chat,
  getDocuments,
  getLogs,
  getTools,
  readFile,
  runTerminal,
  searchFiles,
  transcribeSpeech,
  uploadDocument,
} from "./api/dexterApi";
import PendingApprovals from "./components/PendingApprovals";
import JobsPage from "./pages/JobsPage";
import "./index.css";

type Message = {
  role: "user" | "dexter";
  content: string;
};

type Page =
  | "command"
  | "jobs"
  | "conversations"
  | "files"
  | "tools"
  | "terminal"
  | "memory"
  | "calendar"
  | "settings";

type ToolInfo = {
  description?: string;
  enabled?: boolean;
};

type ToolsMap = Record<string, ToolInfo>;

type ToolAuditItem = {
  tool: string;
  ok?: boolean;
  enabled?: boolean;
  handler_ok?: boolean;
  smoke_status?: string;
  summary?: string;
  handler_error?: string;
};

type ToolAudit = {
  ok?: boolean;
  total?: number;
  passed?: number;
  skipped?: number;
  failed?: number;
  results?: ToolAuditItem[];
};

type UploadedDocument = {
  id: string;
  original_name: string;
  kind?: string;
  size_bytes?: number;
  uploaded_at?: string;
};

function useAutoScroll<T extends HTMLElement>(deps: DependencyList) {
  const ref = useRef<T | null>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    requestAnimationFrame(() => {
      element.scrollTo({
        top: element.scrollHeight,
        behavior: "smooth",
      });
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return ref;
}

function App() {
  const [activePage, setActivePage] = useState<Page>("command");

  const [messages, setMessages] = useState<Message[]>([
    {
      role: "dexter",
      content:
        "Dexter Core online and ready.\nYou can ask me anything, inspect files, run approved commands, or review audit logs.",
    },
  ]);

  const [input, setInput] = useState("");
  const [tools, setTools] = useState<ToolsMap>({});
  const [logs, setLogs] = useState<string[]>([]);
  const [terminalCommand, setTerminalCommand] = useState("git status");
  const [terminalOutput, setTerminalOutput] = useState("");
  const [searchQuery, setSearchQuery] = useState("Dexter");
  const [fileMatches, setFileMatches] = useState<string[]>([]);
  const [filePath, setFilePath] = useState("README.md");
  const [fileContent, setFileContent] = useState("");
  const [documents, setDocuments] = useState<UploadedDocument[]>([]);
  const [documentStatus, setDocumentStatus] = useState("");
  const [toolAudit, setToolAudit] = useState<ToolAudit | null>(null);
  const [toolAuditStatus, setToolAuditStatus] = useState("");
  const [dictationStatus, setDictationStatus] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioStreamRef = useRef<MediaStream | null>(null);

  async function refreshTools() {
    const data = await getTools();
    setTools(data.tools ?? {});
  }

  async function refreshLogs() {
    const data = await getLogs();
    setLogs(data.logs ?? []);
  }

  async function refreshDocuments() {
    const data = await getDocuments();
    setDocuments(data.documents ?? []);
  }

  async function runToolAudit() {
    setToolAuditStatus("Running safe tool audit...");

    try {
      const data = await auditTools();
      setToolAudit(data);
      setToolAuditStatus(
        `Audit complete: ${data.passed ?? 0} passed, ${data.skipped ?? 0} skipped, ${data.failed ?? 0} failed.`,
      );
    } catch (error) {
      setToolAuditStatus(error instanceof Error ? error.message : "Tool audit failed.");
    }
  }

  async function sendMessage(messageOverride?: string) {
    const clean = (messageOverride ?? input).trim();
    if (!clean) return;

    setMessages((prev) => [...prev, { role: "user", content: clean }]);
    setInput("");

    const data = await chat(clean);
    const dexterReply = data.response ?? "No response from Dexter.";

    setMessages((prev) => [
      ...prev,
      { role: "dexter", content: dexterReply },
    ]);

    refreshLogs();
  }

  async function handleTerminal(commandOverride?: string) {
    const cmd = commandOverride ?? terminalCommand;
    setTerminalCommand(cmd);

    const data = await runTerminal(cmd);
    setTerminalOutput(data.output ?? data.error ?? "No output.");
    refreshLogs();
  }

  async function handleSearch() {
    const data = await searchFiles(searchQuery);
    setFileMatches(data.matches ?? []);
  }

  async function handleRead(pathOverride?: string) {
    const target = pathOverride ?? filePath;
    const data = await readFile(target);

    if (data.ok) {
      setFilePath(data.path ?? target);
      setFileContent(data.content);
    } else {
      setFilePath(target);
      setFileContent(data.error ?? "Unable to read file.");
    }
  }

  async function handleDocumentUpload(files: FileList | null) {
    if (!files?.length) return;

    setDocumentStatus(`Uploading ${files.length} document(s)...`);

    try {
      const uploaded = [];
      for (const file of Array.from(files)) {
        const result = await uploadDocument(file, "resume");
        if (!result.ok) {
          throw new Error(result.error ?? `Upload failed for ${file.name}`);
        }
        uploaded.push(result.document?.original_name ?? file.name);
      }

      setDocumentStatus(`Uploaded: ${uploaded.join(", ")}`);
      await refreshDocuments();
    } catch (error) {
      setDocumentStatus(error instanceof Error ? error.message : "Upload failed.");
    }
  }

  async function startDictation() {
    if (!navigator.mediaDevices?.getUserMedia) {
      setDictationStatus("Microphone recording is not available in this browser.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const preferredType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const recorder = new MediaRecorder(stream, { mimeType: preferredType });

      audioChunksRef.current = [];
      audioStreamRef.current = stream;
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        setIsRecording(false);
        setDictationStatus("Transcribing...");
        audioStreamRef.current?.getTracks().forEach((track) => track.stop());
        audioStreamRef.current = null;

        try {
          const audioBlob = new Blob(audioChunksRef.current, {
            type: recorder.mimeType || "audio/webm",
          });
          const result = await transcribeSpeech(audioBlob);

          if (!result.ok) {
            throw new Error(result.error ?? "Could not transcribe speech.");
          }

          const text = String(result.text ?? "").trim();
          if (text) {
            setInput((prev) => (prev.trim() ? `${prev}\n${text}` : text));
            setDictationStatus(`Dictation added via ${result.engine ?? "speech-to-text"}.`);
          } else {
            setDictationStatus("No speech detected.");
          }
        } catch (error) {
          setDictationStatus(error instanceof Error ? error.message : "Dictation failed.");
        } finally {
          audioChunksRef.current = [];
        }
      };

      recorder.start();
      setIsRecording(true);
      setDictationStatus("Recording...");
    } catch (error) {
      setDictationStatus(error instanceof Error ? error.message : "Microphone permission failed.");
    }
  }

  function stopDictation() {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    }
  }

  function toggleDictation() {
    if (isRecording) {
      stopDictation();
    } else {
      startDictation();
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      refreshTools();
      refreshLogs();
      refreshDocuments();
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <main className="app-shell">
      <Sidebar
        activePage={activePage}
        setActivePage={setActivePage}
        toolsCount={Object.keys(tools).length}
      />

      {activePage === "command" && (
        <>
          <CommandCenter
            messages={messages}
            input={input}
            setInput={setInput}
            sendMessage={sendMessage}
            handleTerminal={handleTerminal}
            handleDocumentUpload={handleDocumentUpload}
            documentStatus={documentStatus}
            dictationStatus={dictationStatus}
            isRecording={isRecording}
            toggleDictation={toggleDictation}
            terminalCommand={terminalCommand}
            setTerminalCommand={setTerminalCommand}
            terminalOutput={terminalOutput}
            handleSearch={handleSearch}
            refreshLogs={refreshLogs}
          />

          <RightBar
            tools={tools}
            refreshTools={refreshTools}
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
            handleSearch={handleSearch}
            fileMatches={fileMatches}
            handleRead={handleRead}
            filePath={filePath}
            setFilePath={setFilePath}
            fileContent={fileContent}
            documents={documents}
            documentStatus={documentStatus}
            logs={logs}
            refreshLogs={refreshLogs}
          />
        </>
      )}

      {activePage === "files" && (
        <FilesPage
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
          handleSearch={handleSearch}
          fileMatches={fileMatches}
          handleRead={handleRead}
          filePath={filePath}
          setFilePath={setFilePath}
          fileContent={fileContent}
        />
      )}

      {activePage === "tools" && (
        <ToolsPage
          tools={tools}
          refreshTools={refreshTools}
          runToolAudit={runToolAudit}
          toolAudit={toolAudit}
          toolAuditStatus={toolAuditStatus}
        />
      )}

      {activePage === "terminal" && (
        <TerminalPage
          terminalCommand={terminalCommand}
          setTerminalCommand={setTerminalCommand}
          handleTerminal={handleTerminal}
          terminalOutput={terminalOutput}
        />
      )}

      {activePage === "jobs" && <JobsPage onSendMessage={sendMessage} />}

      {activePage !== "command" &&
        activePage !== "jobs" &&
        activePage !== "files" &&
        activePage !== "tools" &&
        activePage !== "terminal" && <PlaceholderPage page={activePage} />}
    </main>
  );
}

function Sidebar({
  activePage,
  setActivePage,
  toolsCount,
}: {
  activePage: Page;
  setActivePage: (page: Page) => void;
  toolsCount: number;
}) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <h1>DEXTER</h1>
        <p>AI ASSISTANT</p>
      </div>

      <nav className="nav-list">
        <NavButton
          active={activePage === "command"}
          onClick={() => setActivePage("command")}
          icon={<LayoutDashboard size={18} />}
          label="Command Center"
        />
        <NavButton
          active={activePage === "conversations"}
          onClick={() => setActivePage("conversations")}
          icon={<Bot size={18} />}
          label="Conversations"
        />
        <NavButton
          active={activePage === "jobs"}
          onClick={() => setActivePage("jobs")}
          icon={<BriefcaseBusiness size={18} />}
          label="Jobs"
        />
        <NavButton
          active={activePage === "files"}
          onClick={() => setActivePage("files")}
          icon={<Files size={18} />}
          label="Files & Folders"
        />
        <NavButton
          active={activePage === "tools"}
          onClick={() => setActivePage("tools")}
          icon={<Wrench size={18} />}
          label="Tools"
        />
        <NavButton
          active={activePage === "terminal"}
          onClick={() => setActivePage("terminal")}
          icon={<Terminal size={18} />}
          label="Terminal"
        />
        <NavButton
          active={activePage === "memory"}
          onClick={() => setActivePage("memory")}
          icon={<MemoryStick size={18} />}
          label="Memory"
        />
        <NavButton
          active={activePage === "calendar"}
          onClick={() => setActivePage("calendar")}
          icon={<Calendar size={18} />}
          label="Calendar"
        />
        <NavButton
          active={activePage === "settings"}
          onClick={() => setActivePage("settings")}
          icon={<Settings size={18} />}
          label="Settings"
        />
      </nav>

      <section className="mini-panel sidebar-status">
        <h3>System Status</h3>
        <div className="status-row">
          <Shield size={16} />
          <span>Dexter Core</span>
          <b>Online</b>
        </div>
        <div className="status-row">
          <Bot size={16} />
          <span>Backend</span>
          <b>Connected</b>
        </div>
        <div className="status-row">
          <MemoryStick size={16} />
          <span>Memory</span>
          <b>Active</b>
        </div>
        <div className="status-row">
          <Wrench size={16} />
          <span>Tools</span>
          <b>{toolsCount}</b>
        </div>
      </section>

      <div className="user-card">
        <div className="avatar">V</div>
        <div>
          <strong>Vishal</strong>
          <p>Administrator</p>
        </div>
      </div>
    </aside>
  );
}

function NavButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: ReactNode;
  label: string;
}) {
  return (
    <button className={`nav-item ${active ? "active" : ""}`} onClick={onClick}>
      {icon} {label}
    </button>
  );
}

function CommandCenter({
  messages,
  input,
  setInput,
  sendMessage,
  handleTerminal,
  handleDocumentUpload,
  documentStatus,
  dictationStatus,
  isRecording,
  toggleDictation,
  terminalCommand,
  setTerminalCommand,
  terminalOutput,
  handleSearch,
  refreshLogs,
}: {
  messages: Message[];
  input: string;
  setInput: (value: string) => void;
  sendMessage: (messageOverride?: string) => void;
  handleTerminal: (commandOverride?: string) => void;
  handleDocumentUpload: (files: FileList | null) => void;
  documentStatus: string;
  dictationStatus: string;
  isRecording: boolean;
  toggleDictation: () => void;
  terminalCommand: string;
  setTerminalCommand: (value: string) => void;
  terminalOutput: string;
  handleSearch: () => void;
  refreshLogs: () => void;
}) {
  const messagesRef = useAutoScroll<HTMLDivElement>([
    messages,
    documentStatus,
    dictationStatus,
  ]);

  return (
    <section className="center">
      <header className="top-card">
        <div>
          <h2>Welcome back, Vishal</h2>
          <p>How can I help you today?</p>
        </div>
        <div className="time-block">
          <span>Dexter v0.1</span>
          <strong>LOCAL</strong>
        </div>
      </header>

      <section className="chat-card command-chat-card">
        <div className="card-header">
          <div>
            <span className="online-dot" />
            <strong>DEXTER</strong>
          </div>
          <span>Core Interface</span>
        </div>

        <div className="messages" ref={messagesRef}>
          {messages.map((message, index) => (
            <div key={index} className={`message ${message.role}`}>
              <div className="message-icon">
                {message.role === "dexter" ? "D" : "V"}
              </div>
              <div>
                <span className="message-role">{message.role}</span>
                <pre>{message.content}</pre>
              </div>
            </div>
          ))}
        </div>

        <div className="chat-input-row">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
              }
            }}
            placeholder="Type a command, like apply for the latest SWE internships..."
            rows={3}
          />
          <button
            className={isRecording ? "dictation-button recording" : "dictation-button"}
            onClick={toggleDictation}
            title={isRecording ? "Stop dictation" : "Record speech to text"}
            aria-label={isRecording ? "Stop dictation" : "Record speech to text"}
          >
            {isRecording ? <Square size={18} /> : <Mic size={18} />}
          </button>
          <button onClick={() => sendMessage()}>
            <Send size={18} />
          </button>
        </div>

        <div className="quick-actions">
          <label className="upload-doc-button">
            <Upload size={15} /> Upload Docs
            <input
              type="file"
              accept=".pdf,.doc,.docx,.txt,.md,.rtf"
              multiple
              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                handleDocumentUpload(event.currentTarget.files);
                event.currentTarget.value = "";
              }}
            />
          </label>
          <button onClick={() => sendMessage("Apply for the latest SWE internships")}>
            <BriefcaseBusiness size={15} /> SWE Internships
          </button>
          <button onClick={() => sendMessage("Apply for the latest SWE jobs")}>
            <BriefcaseBusiness size={15} /> Latest SWE Jobs
          </button>
          <button onClick={() => handleTerminal("ls")}>
            <List size={15} /> List Files
          </button>
          <button onClick={() => handleTerminal("git status")}>
            <GitBranch size={15} /> Git Status
          </button>
          <button onClick={handleSearch}>
            <FolderSearch size={15} /> Search Code
          </button>
          <button onClick={() => handleTerminal("pwd")}>
            <Terminal size={15} /> Working Dir
          </button>
          <button onClick={refreshLogs}>
            <History size={15} /> Show Logs
          </button>
        </div>

        {documentStatus && <div className="doc-status">{documentStatus}</div>}
        {dictationStatus && <div className="dictation-status">{dictationStatus}</div>}
      </section>

      <section className="terminal-card">
        <TerminalPanel
          terminalCommand={terminalCommand}
          setTerminalCommand={setTerminalCommand}
          handleTerminal={handleTerminal}
          terminalOutput={terminalOutput}
        />
      </section>
    </section>
  );
}

function RightBar({
  tools,
  refreshTools,
  searchQuery,
  setSearchQuery,
  handleSearch,
  fileMatches,
  handleRead,
  filePath,
  setFilePath,
  fileContent,
  documents,
  documentStatus,
  logs,
  refreshLogs,
}: {
  tools: ToolsMap;
  refreshTools: () => void;
  searchQuery: string;
  setSearchQuery: (value: string) => void;
  handleSearch: () => void;
  fileMatches: string[];
  handleRead: (pathOverride?: string) => void;
  filePath: string;
  setFilePath: (value: string) => void;
  fileContent: string;
  documents: UploadedDocument[];
  documentStatus: string;
  logs: string[];
  refreshLogs: () => void;
}) {
  const documentsRef = useAutoScroll<HTMLDivElement>([documents, documentStatus]);
  const sidebarFileResultsRef = useAutoScroll<HTMLDivElement>([fileMatches]);
  const filePreviewRef = useAutoScroll<HTMLPreElement>([fileContent]);
  const activityRef = useAutoScroll<HTMLDivElement>([logs]);

  return (
    <aside className="rightbar">
      <section className="mini-panel">
        <h3>
          <Gauge size={18} /> System Overview
        </h3>
        <Metric label="CPU Usage" value="Local" width="42%" />
        <Metric label="RAM Usage" value="Local" width="32%" />
        <Metric label="Disk Usage" value="Project" width="55%" />
        <Metric label="Uptime" value="Active Session" width="78%" />
      </section>

      <section className="mini-panel">
        <div className="panel-title-row">
          <h3>
            <Wrench size={18} /> Tools
          </h3>
          <button onClick={refreshTools}>Refresh</button>
        </div>

        <ToolList tools={tools} />
      </section>

      <PendingApprovals />

      <section className="mini-panel">
        <h3>
          <FileText size={18} /> Documents
        </h3>
        {documentStatus && <p className="doc-panel-status">{documentStatus}</p>}
        <div className="doc-list scroll-panel" ref={documentsRef}>
          {documents.slice(0, 5).map((document) => (
            <div className="doc-row" key={`${document.id}-${document.original_name}`}>
              <span>{document.original_name}</span>
              <b>{document.kind ?? "doc"}</b>
            </div>
          ))}
          {!documents.length && <p>No resume/docs uploaded yet.</p>}
        </div>
      </section>

      <section className="mini-panel">
        <h3>
          <FolderSearch size={18} /> File Search
        </h3>
        <div className="compact-input-row">
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search project..."
          />
          <button onClick={handleSearch}>Go</button>
        </div>

        <div className="file-results scroll-panel" ref={sidebarFileResultsRef}>
          {fileMatches.slice(0, 8).map((match) => (
            <button key={match} onClick={() => handleRead(match)}>
              {match}
            </button>
          ))}
        </div>
      </section>

      <section className="mini-panel">
        <h3>
          <Files size={18} /> File Viewer
        </h3>
        <div className="compact-input-row">
          <input value={filePath} onChange={(e) => setFilePath(e.target.value)} />
          <button onClick={() => handleRead()}>Read</button>
        </div>
        <pre className="file-preview" ref={filePreviewRef}>
          {fileContent || "No file loaded."}
        </pre>
      </section>

      <section className="mini-panel activity-panel">
        <div className="panel-title-row">
          <h3>
            <CheckCircle2 size={18} /> Recent Activity
          </h3>
          <button onClick={refreshLogs}>View</button>
        </div>

        <div className="activity-list scroll-panel" ref={activityRef}>
          {logs.slice(-6).map((log, index) => (
            <div className="activity-item" key={index}>
              <span />
              <p>{log}</p>
            </div>
          ))}
        </div>
      </section>
    </aside>
  );
}

function FilesPage({
  searchQuery,
  setSearchQuery,
  handleSearch,
  fileMatches,
  handleRead,
  filePath,
  setFilePath,
  fileContent,
}: {
  searchQuery: string;
  setSearchQuery: (value: string) => void;
  handleSearch: () => void;
  fileMatches: string[];
  handleRead: (pathOverride?: string) => void;
  filePath: string;
  setFilePath: (value: string) => void;
  fileContent: string;
}) {
  const fileResultsRef = useAutoScroll<HTMLDivElement>([fileMatches]);
  const filePagePreviewRef = useAutoScroll<HTMLPreElement>([fileContent]);

  return (
    <section className="center wide-page">
      <section className="chat-card">
        <div className="card-header">
          <div>
            <FolderSearch size={18} />
            <strong>Files & Folders</strong>
          </div>
          <span>Project Browser</span>
        </div>

        <div className="file-page-grid">
          <section className="mini-panel">
            <h3>Search Files</h3>
            <div className="compact-input-row">
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                placeholder="Search files..."
              />
              <button onClick={handleSearch}>Search</button>
            </div>

            <div className="file-results scroll-panel" ref={fileResultsRef}>
              {fileMatches.map((match) => (
                <button key={match} onClick={() => handleRead(match)}>
                  {match}
                </button>
              ))}
            </div>
          </section>

          <section className="mini-panel file-page-viewer">
            <h3>{filePath || "File Viewer"}</h3>
            <div className="compact-input-row">
              <input
                value={filePath}
                onChange={(e) => setFilePath(e.target.value)}
              />
              <button onClick={() => handleRead()}>Read</button>
            </div>
            <pre className="file-page-preview" ref={filePagePreviewRef}>
              {fileContent || "Select a file to view its contents."}
            </pre>
          </section>
        </div>
      </section>
    </section>
  );
}

function ToolsPage({
  tools,
  refreshTools,
  runToolAudit,
  toolAudit,
  toolAuditStatus,
}: {
  tools: ToolsMap;
  refreshTools: () => void;
  runToolAudit: () => void;
  toolAudit: ToolAudit | null;
  toolAuditStatus: string;
}) {
  return (
    <section className="center wide-page">
      <section className="chat-card">
        <div className="card-header">
          <div>
            <Wrench size={18} />
            <strong>Tools</strong>
          </div>
          <div className="header-actions">
            <button onClick={runToolAudit}>Run Audit</button>
            <button onClick={refreshTools}>Refresh</button>
          </div>
        </div>
        {toolAuditStatus && <p className="audit-status">{toolAuditStatus}</p>}
        {toolAudit && <ToolAuditPanel audit={toolAudit} />}
        <ToolList tools={tools} />
      </section>
    </section>
  );
}

function TerminalPage({
  terminalCommand,
  setTerminalCommand,
  handleTerminal,
  terminalOutput,
}: {
  terminalCommand: string;
  setTerminalCommand: (value: string) => void;
  handleTerminal: (commandOverride?: string) => void;
  terminalOutput: string;
}) {
  return (
    <section className="center wide-page">
      <section className="terminal-card">
        <TerminalPanel
          terminalCommand={terminalCommand}
          setTerminalCommand={setTerminalCommand}
          handleTerminal={handleTerminal}
          terminalOutput={terminalOutput}
        />
      </section>
    </section>
  );
}

function TerminalPanel({
  terminalCommand,
  setTerminalCommand,
  handleTerminal,
  terminalOutput,
}: {
  terminalCommand: string;
  setTerminalCommand: (value: string) => void;
  handleTerminal: (commandOverride?: string) => void;
  terminalOutput: string;
}) {
  const terminalOutputRef = useAutoScroll<HTMLPreElement>([terminalOutput]);

  return (
    <>
      <div className="card-header">
        <div>
          <Terminal size={18} />
          <strong>TERMINAL</strong>
        </div>
        <span>Approved Commands Only</span>
      </div>

      <div className="terminal-input-row">
        <span>vishal@Dexter:~/Dexter $</span>
        <input
          value={terminalCommand}
          onChange={(e) => setTerminalCommand(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleTerminal()}
        />
        <button onClick={() => handleTerminal()}>Run</button>
      </div>

      <pre className="terminal-output" ref={terminalOutputRef}>
        {terminalOutput || "No terminal command run yet."}
      </pre>
    </>
  );
}

function ToolList({ tools }: { tools: ToolsMap }) {
  return (
    <div className="tool-list">
      {Object.entries(tools).map(([name, value]) => (
        <div className="tool-row" key={name}>
          <Code2 size={16} />
          <span>{name}</span>
          <b className={value.enabled ? "on" : "off"}>
            {value.enabled ? "ON" : "OFF"}
          </b>
        </div>
      ))}
    </div>
  );
}

function ToolAuditPanel({ audit }: { audit: ToolAudit }) {
  const results = audit.results ?? [];

  return (
    <div className="audit-panel">
      <div className="audit-summary">
        <span>{audit.total ?? results.length} tools</span>
        <span>{audit.passed ?? 0} passed</span>
        <span>{audit.skipped ?? 0} skipped</span>
        <span>{audit.failed ?? 0} failed</span>
      </div>

      <div className="audit-list scroll-panel">
        {results.map((item) => (
          <div className="audit-row" key={item.tool}>
            <Code2 size={15} />
            <div>
              <strong>{item.tool}</strong>
              <p>{item.summary || item.handler_error || item.smoke_status}</p>
            </div>
            <b className={item.ok ? "on" : "off"}>
              {item.smoke_status?.replaceAll("_", " ") ?? (item.ok ? "ok" : "fail")}
            </b>
          </div>
        ))}
      </div>
    </div>
  );
}

function PlaceholderPage({ page }: { page: Page }) {
  return (
    <section className="center wide-page">
      <section className="chat-card">
        <div className="card-header">
          <div>
            <strong>{pageTitle(page)}</strong>
          </div>
          <span>Coming soon</span>
        </div>

        <div className="messages">
          <div className="message dexter">
            <div className="message-icon">D</div>
            <div>
              <span className="message-role">dexter</span>
              <pre>
                This page is reserved for {pageTitle(page)}. We will wire this
                into real functionality next.
              </pre>
            </div>
          </div>
        </div>
      </section>
    </section>
  );
}

function Metric({
  label,
  value,
  width,
}: {
  label: string;
  value: string;
  width: string;
}) {
  return (
    <div className="metric">
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
      <div className="bar">
        <div style={{ width }} />
      </div>
    </div>
  );
}

function pageTitle(page: Page) {
  const titles: Record<Page, string> = {
    command: "Command Center",
    jobs: "Jobs",
    conversations: "Conversations",
    files: "Files & Folders",
    tools: "Tools",
    terminal: "Terminal",
    memory: "Memory",
    calendar: "Calendar",
    settings: "Settings",
  };

  return titles[page];
}

export default App;
