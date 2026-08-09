import { useRef } from 'react'
import './LeftSidebar.css'

export default function LeftSidebar({ companies, onSelectPdf, selectedPdf, onUpload, open, onToggle }) {
  const inputRef = useRef()

  const handleFile = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    const form = new FormData()
    form.append('file', file)
    await fetch('http://localhost:8000/upload', { method: 'POST', body: form })
    onUpload()
    e.target.value = ''
  }

  return (
    <div className={`left-sidebar ${open ? 'open' : 'collapsed'}`}>
      <div className="sidebar-header">
        {open && <span className="sidebar-title">Documents</span>}
        {open && (
          <button className="upload-btn" onClick={() => inputRef.current.click()}>+ Upload</button>
        )}
        <button className="toggle-btn" onClick={onToggle} title={open ? 'Hide sidebar' : 'Show sidebar'}>
          {open ? '◀' : '▶'}
        </button>
        <input ref={inputRef} type="file" accept=".pdf" style={{ display: 'none' }} onChange={handleFile} />
      </div>

      {open && (
        <div className="file-list">
          {Object.entries(companies).map(([company, files]) => (
            <div key={company} className="company-group">
              <div className="company-name">{company}</div>
              {files.map(f => (
                <div
                  key={f.filename}
                  className={`file-item ${selectedPdf === f.filename ? 'selected' : ''}`}
                  onClick={() => onSelectPdf(f.filename === selectedPdf ? null : f.filename)}
                >
                  <span className="file-year">{f.year}</span>
                  <span className="file-name">{f.filename}</span>
                  <span className="file-size">{f.size_kb}kb</span>
                </div>
              ))}
            </div>
          ))}
          {Object.keys(companies).length === 0 && (
            <div className="empty-hint">No documents yet.<br />Upload a PDF to get started.</div>
          )}
        </div>
      )}
    </div>
  )
}
