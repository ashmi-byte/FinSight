import { useState, useEffect } from 'react'
import './ReasoningPanel.css'

const STEP_LABELS = {
  classify:  'Classifying query',
  decompose: 'Breaking into sub-questions',
  retrieve:  'Retrieving data',
  evaluate:  'Evaluating results',
  rewrite:   'Rewriting search query',
  answer:    'Generating answer',
}

export default function ReasoningPanel({ steps, isComplete }) {
  const [collapsed, setCollapsed] = useState(false)

  // Auto-collapse when answer is ready
  useEffect(() => {
    if (isComplete) setCollapsed(true)
  }, [isComplete])

  if (steps.length === 0) return null

  return (
    <div className={`reasoning-panel ${isComplete ? 'complete' : ''}`}>
      <div className="reasoning-header" onClick={() => setCollapsed(c => !c)}>
        <span className="reasoning-title">
          {isComplete ? '✓ Reasoning process' : '⟳ Thinking...'}
        </span>
        <span className="collapse-btn">{collapsed ? '▼' : '▲'}</span>
      </div>

      {!collapsed && (
        <div className="reasoning-steps">
          {steps.map((step, i) => (
            <div key={i} className={`step step-${step.event}`}>
              <div className="step-label">{STEP_LABELS[step.event] || step.event}</div>
              <StepDetail event={step.event} data={step.data} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function StepDetail({ event, data }) {
  if (event === 'classify') {
    return (
      <div className="step-detail">
        Type: <b>{data.query_type}</b> · Mode: <b>{data.mode}</b>
      </div>
    )
  }

  if (event === 'decompose') {
    return (
      <div className="step-detail">
        {data.sub_questions?.map((sq, i) => (
          <div key={i} className="sub-question">
            <span className={`mode-badge mode-${sq.mode}`}>{sq.mode}</span>
            {sq.question}
          </div>
        ))}
      </div>
    )
  }

  if (event === 'retrieve') {
    return (
      <div className="step-detail">
        {data.sub_questions?.map((sq, i) => (
          <div key={i} className="sub-question">
            <span className="retrieve-info">
              {sq.sql_hit ? '🗄 SQL ✓' : ''} {sq.vector_hits > 0 ? `📄 ${sq.vector_hits} chunks` : ''}
            </span>
            {sq.question}
          </div>
        ))}
      </div>
    )
  }

  if (event === 'evaluate') {
    return (
      <div className="step-detail">
        {data.sub_questions?.map((sq, i) => (
          <div key={i} className="sub-question">
            <span className={`status-badge status-${sq.status}`}>{sq.status}</span>
            {sq.score !== undefined && <span className="score">score: {sq.score}</span>}
            {sq.question}
          </div>
        ))}
      </div>
    )
  }

  if (event === 'rewrite') {
    return (
      <div className="step-detail">
        {data.sub_questions?.map((sq, i) => (
          <div key={i} className="sub-question">
            <span className="rewrite-label">new query:</span> {sq.new_search_query}
          </div>
        ))}
      </div>
    )
  }

  return null
}
