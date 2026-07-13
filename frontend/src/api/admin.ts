import client from './client'

export type DocStatus = 'parsing' | 'indexed' | 'failed'

export interface DocumentItem {
  id: number
  filename: string
  file_type: string
  doc_type: string
  status: DocStatus
  chunk_count: number
  error_msg: string | null
  created_at: string
}

export interface VectorStats {
  collection: string
  vector_count: number
  document_count: number
}

export interface ChunkPreview {
  index: number
  content: string
  length: number
}

export const adminApi = {
  listDocuments: () => client.get<DocumentItem[]>('/admin/documents'),

  getDocument: (id: number) => client.get<DocumentItem>(`/admin/documents/${id}`),

  uploadDocument: (file: File, docType: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('doc_type', docType)
    return client.post<DocumentItem>('/admin/documents', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
  },

  reindexDocument: (id: number) =>
    client.post<DocumentItem>(`/admin/documents/${id}/reindex`),

  deleteDocument: (id: number) => client.delete(`/admin/documents/${id}`),

  previewChunks: (text: string, chunkSize: number, chunkOverlap: number) =>
    client.post<ChunkPreview[]>('/admin/documents/preview-chunks', {
      text,
      chunk_size: chunkSize,
      chunk_overlap: chunkOverlap,
    }),

  vectorStats: () => client.get<VectorStats>('/admin/vector/stats'),
}
