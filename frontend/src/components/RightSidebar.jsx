import './RightSidebar.css'

export default function RightSidebar({ selectedPdf, open, onClose }) {
  return (
    <div className={`right-sidebar ${open ? 'open' : ''}`}>
      <div className="sidebar-header">
        <span className="sidebar-title">{selectedPdf || ''}</span>
        <button className="close-btn" onClick={onClose}>✕</button>
      </div>
      {selectedPdf && open && (
        <iframe
          className="pdf-viewer"
          src={`http://localhost:8000/pdf/${encodeURIComponent(selectedPdf)}`}
          title="PDF Viewer"
        />
      )}
    </div>
  )
}
