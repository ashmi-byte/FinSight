import { useState, useEffect } from 'react'
import LeftSidebar from './components/LeftSidebar'
import ChatArea from './components/ChatArea'
import RightSidebar from './components/RightSidebar'
import './App.css'

export default function App() {
  const [companies, setCompanies] = useState({})
  const [selectedPdf, setSelectedPdf] = useState(null)
  const [leftOpen, setLeftOpen] = useState(true)
  const [rightOpen, setRightOpen] = useState(false)

  const loadFiles = async () => {
    const res = await fetch('http://localhost:8000/files')
    const data = await res.json()
    setCompanies(data.companies)
  }

  useEffect(() => { loadFiles() }, [])

  const handleSelectPdf = (filename) => {
    setSelectedPdf(filename)
    setRightOpen(!!filename)
  }

  return (
    <div className="app">
      <LeftSidebar
        companies={companies}
        selectedPdf={selectedPdf}
        onSelectPdf={handleSelectPdf}
        onUpload={loadFiles}
        open={leftOpen}
        onToggle={() => setLeftOpen(o => !o)}
      />
      <ChatArea
        leftOpen={leftOpen}
        rightOpen={rightOpen}
        onToggleLeft={() => setLeftOpen(o => !o)}
        onToggleRight={() => setRightOpen(o => !o)}
      />
      <RightSidebar
        selectedPdf={selectedPdf}
        open={rightOpen}
        onClose={() => setRightOpen(false)}
      />
    </div>
  )
}
