import { useCallback, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, FileText, X, CheckCircle, AlertCircle, Loader2 } from 'lucide-react'
import { useStore } from '../store'
import clsx from 'clsx'

interface UploadFile {
  file:     File
  id:       string
  status:   'pending' | 'uploading' | 'processing' | 'done' | 'error'
  progress: number
  error?:   string
}

function uid() { return Math.random().toString(36).slice(2) }

interface Props { onUploaded?: () => void }

export function DocumentUpload({ onUploaded }: Props) {
  const [files, setFiles] = useState<UploadFile[]>([])
  const { addDocument }   = useStore()

  const processFile = async (uf: UploadFile) => {
    // Step 1: Upload file to S3 via backend
    setFiles((prev) => prev.map((f) =>
      f.id === uf.id ? { ...f, status: 'uploading', progress: 20 } : f
    ))

    try {
      const form = new FormData()
      form.append('file', uf.file)

      const uploadResp = await fetch('/api/documents/upload', {
        method: 'POST',
        body:   form,
      })

      if (!uploadResp.ok) {
        const err = await uploadResp.text()
        throw new Error(`Upload failed: ${err}`)
      }

      const uploadResult = await uploadResp.json()
      const s3Key        = uploadResult.s3_key || `bids/${uf.file.name}`

      setFiles((prev) => prev.map((f) =>
        f.id === uf.id ? { ...f, status: 'processing', progress: 60 } : f
      ))

      // Trigger document processing and WAIT for it to complete
      // This is synchronous - Lambda runs up to 15 min, we wait for chunks to be stored
      const processResp = await fetch('/api/documents', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          document_path: s3Key,
          document_type: uf.file.name.toLowerCase().endsWith('.pdf') ? 'pdf' : 'txt',
        }),
      })

      const processResult = processResp.ok ? await processResp.json() : {}
      const chunksCreated = processResult?.chunks_created ?? 0
      console.log('Process result:', processResult)

      // If no chunks were created, the PDF may need more time - retry once
      if (chunksCreated === 0 && processResp.ok) {
        console.log('No chunks on first attempt, retrying...')
        await new Promise((r) => setTimeout(r, 3000))
        const retryResp = await fetch('/api/documents', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({
            document_path: s3Key,
            document_type: uf.file.name.toLowerCase().endsWith('.pdf') ? 'pdf' : 'txt',
          }),
        })
        const retryResult = retryResp.ok ? await retryResp.json() : {}
        Object.assign(processResult, retryResult)
      }

      setFiles((prev) => prev.map((f) =>
        f.id === uf.id ? { ...f, status: 'done', progress: 100 } : f
      ))

      // Add to store with the S3 key as the document ID for extraction
      addDocument({
        id:          s3Key,
        name:        uf.file.name,
        s3_key:      s3Key,
        status:      'ready',
        chunks:      processResult?.chunks_created ?? 0,
        pages:       processResult?.pages_approx,
        uploaded_at: new Date().toISOString(),
        size_bytes:  uf.file.size,
      })
      onUploaded?.()  // refresh parent document list

    } catch (err: any) {
      console.error('Upload error:', err)
      setFiles((prev) => prev.map((f) =>
        f.id === uf.id
          ? { ...f, status: 'error', error: err?.message || 'Upload failed' }
          : f
      ))
    }
  }

  const onDrop = useCallback((accepted: File[]) => {
    const newFiles: UploadFile[] = accepted.map((file) => ({
      file, id: uid(), status: 'pending', progress: 0,
    }))
    setFiles((prev) => [...prev, ...newFiles])
    newFiles.forEach(processFile)
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf':  ['.pdf'],
      'text/plain':       ['.txt'],
      'application/msword': ['.doc', '.docx'],
    },
    maxSize: 100 * 1024 * 1024,
  })

  const removeFile = (id: string) =>
    setFiles((prev) => prev.filter((f) => f.id !== id))

  return (
    <div className="space-y-4">
      <div
        {...getRootProps()}
        className={clsx(
          'border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-200',
          isDragActive
            ? 'border-brand-500 bg-brand-600/10'
            : 'border-surface-500 hover:border-brand-500/50 hover:bg-surface-700/50'
        )}
      >
        <input {...getInputProps()} />
        <Upload size={32} className={clsx(
          'mx-auto mb-3',
          isDragActive ? 'text-brand-400' : 'text-gray-500'
        )} />
        <p className="text-gray-300 font-medium">
          {isDragActive ? 'Drop files here' : 'Drag & drop bid documents here'}
        </p>
        <p className="text-gray-500 text-sm mt-1">
          PDF, TXT, DOC up to 100 MB — click to browse
        </p>
      </div>

      {files.length > 0 && (
        <div className="space-y-2">
          {files.map((uf) => (
            <div key={uf.id} className="card flex items-center gap-3">
              <FileText size={18} className="text-brand-400 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-200 truncate">{uf.file.name}</p>
                <div className="flex items-center gap-2 mt-1">
                  {uf.status !== 'done' && uf.status !== 'error' && (
                    <div className="flex-1 bg-surface-600 rounded-full h-1">
                      <div
                        className="bg-brand-500 h-1 rounded-full transition-all duration-500"
                        style={{ width: `${uf.progress}%` }}
                      />
                    </div>
                  )}
                  {uf.status === 'error' && (
                    <p className="text-xs text-red-400 truncate">{uf.error}</p>
                  )}
                  <span className="text-xs text-gray-500 shrink-0">
                    {(uf.file.size / 1024 / 1024).toFixed(1)} MB
                  </span>
                </div>
                <p className="text-xs text-gray-600 mt-0.5">
                  {uf.status === 'uploading'  && 'Uploading to S3...'}
                  {uf.status === 'processing' && 'Extracting text & generating embeddings...'}
                  {uf.status === 'done'       && 'Ready for requirements extraction'}
                </p>
              </div>
              <div className="shrink-0">
                {(uf.status === 'uploading' || uf.status === 'processing') && (
                  <Loader2 size={16} className="text-brand-400 animate-spin" />
                )}
                {uf.status === 'done'  && <CheckCircle size={16} className="text-green-400" />}
                {uf.status === 'error' && <AlertCircle size={16} className="text-red-400" />}
              </div>
              <button
                onClick={() => removeFile(uf.id)}
                className="text-gray-600 hover:text-gray-400"
              >
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
