import { useEffect, useState, useCallback, useRef } from 'react'
import {
  Layout, Button, Typography, Space, Table, Tag, Upload, Modal, Select,
  message as antMessage, Popconfirm, Card, Row, Col, Statistic, Input, Tooltip,
} from 'antd'
import {
  ArrowLeftOutlined, UploadOutlined, DeleteOutlined, ReloadOutlined,
  ExperimentOutlined, DatabaseOutlined, FileTextOutlined, InboxOutlined,
} from '@ant-design/icons'
import type { UploadFile } from 'antd'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/store/auth'
import {
  adminApi, type DocumentItem, type VectorStats, type ChunkPreview,
} from '@/api/admin'

const { Header, Content } = Layout
const { Title, Text, Paragraph } = Typography

// 知识库分类，与后端 splitter 篇名分类保持一致
const DOC_TYPES = [
  '自动分类', 'Java基础', 'Java进阶', 'JVM', 'Spring全家桶',
  '数据库与中间件', '微服务', '数据结构与算法', '未分类',
]

const STATUS_MAP: Record<string, { color: string; text: string }> = {
  parsing: { color: 'processing', text: '解析入库中' },
  indexed: { color: 'success', text: '已入库' },
  failed: { color: 'error', text: '失败' },
}

export default function AdminPage() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)

  const [docs, setDocs] = useState<DocumentItem[]>([])
  const [stats, setStats] = useState<VectorStats | null>(null)
  const [loading, setLoading] = useState(false)

  // 上传对话框
  const [uploadOpen, setUploadOpen] = useState(false)
  const [uploadFile, setUploadFile] = useState<UploadFile | null>(null)
  const [uploadType, setUploadType] = useState('自动分类')
  const [uploading, setUploading] = useState(false)

  // 分段预览对话框
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewText, setPreviewText] = useState('')
  const [chunkSize, setChunkSize] = useState(500)
  const [chunkOverlap, setChunkOverlap] = useState(50)
  const [previewResult, setPreviewResult] = useState<ChunkPreview[]>([])
  const [previewing, setPreviewing] = useState(false)

  // 轮询：有 parsing 状态的文档时定时刷新
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const loadData = useCallback(async () => {
    const [d, s] = await Promise.all([adminApi.listDocuments(), adminApi.vectorStats()])
    setDocs(d.data)
    setStats(s.data)
    return d.data
  }, [])

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      await loadData()
    } finally {
      setLoading(false)
    }
  }, [loadData])

  useEffect(() => {
    refresh()
  }, [refresh])

  // 有文档在解析中则每 3 秒轮询，全部结束后停止
  useEffect(() => {
    const hasParsing = docs.some((d) => d.status === 'parsing')
    if (hasParsing && !pollRef.current) {
      pollRef.current = setInterval(loadData, 3000)
    } else if (!hasParsing && pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }, [docs, loadData])

  const onUpload = async () => {
    if (!uploadFile) {
      antMessage.warning('请先选择文件')
      return
    }
    setUploading(true)
    try {
      const docType = uploadType === '自动分类' ? '未分类' : uploadType
      await adminApi.uploadDocument(uploadFile as unknown as File, docType)
      antMessage.success('已上传，正在后台解析入库')
      setUploadOpen(false)
      setUploadFile(null)
      setUploadType('自动分类')
      await loadData()
    } catch {
      /* 拦截器已提示 */
    } finally {
      setUploading(false)
    }
  }

  const onReindex = async (id: number) => {
    try {
      await adminApi.reindexDocument(id)
      antMessage.success('已触发重新入库')
      await loadData()
    } catch {
      /* 拦截器已提示 */
    }
  }

  const onDelete = async (id: number) => {
    try {
      await adminApi.deleteDocument(id)
      antMessage.success('已删除')
      await loadData()
    } catch {
      /* 拦截器已提示 */
    }
  }

  const onPreview = async () => {
    if (!previewText.trim()) {
      antMessage.warning('请输入待分段的文本')
      return
    }
    const size = Math.min(2000, Math.max(100, chunkSize || 100))
    const overlap = Math.min(500, Math.max(0, chunkOverlap || 0))
    setPreviewing(true)
    try {
      const { data } = await adminApi.previewChunks(previewText, size, overlap)
      setPreviewResult(data)
    } catch {
      /* 拦截器已提示 */
    } finally {
      setPreviewing(false)
    }
  }

  const columns = [
    {
      title: '文件名',
      dataIndex: 'filename',
      render: (v: string) => (
        <Space size={4}>
          <FileTextOutlined style={{ color: '#1677ff' }} />
          <Text ellipsis style={{ maxWidth: 220 }}>{v}</Text>
        </Space>
      ),
    },
    { title: '类型', dataIndex: 'file_type', width: 80,
      render: (v: string) => <Tag>{v.toUpperCase()}</Tag> },
    { title: '分类', dataIndex: 'doc_type', width: 130,
      render: (v: string) => <Tag color="geekblue">{v}</Tag> },
    { title: '分段数', dataIndex: 'chunk_count', width: 90, align: 'center' as const },
    {
      title: '状态', dataIndex: 'status', width: 130,
      render: (v: string, row: DocumentItem) => {
        const s = STATUS_MAP[v] ?? { color: 'default', text: v }
        return v === 'failed' && row.error_msg ? (
          <Tooltip title={row.error_msg}>
            <Tag color={s.color}>{s.text}</Tag>
          </Tooltip>
        ) : (
          <Tag color={s.color}>{s.text}</Tag>
        )
      },
    },
    {
      title: '操作', key: 'action', width: 160,
      render: (_: unknown, row: DocumentItem) => (
        <Space size={4}>
          <Tooltip title="重新入库">
            <Button
              type="text" size="small" icon={<ReloadOutlined />}
              disabled={row.status === 'parsing'}
              onClick={() => onReindex(row.id)}
            />
          </Tooltip>
          <Popconfirm title="删除该文档及其全部向量？" onConfirm={() => onDelete(row.id)}>
            <Button type="text" size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Layout style={{ height: '100%' }}>
      <Header
        style={{
          background: '#fff', borderBottom: '1px solid #f0f0f0', display: 'flex',
          alignItems: 'center', justifyContent: 'space-between', padding: '0 24px',
        }}
      >
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/chat')}>
            返回问答
          </Button>
          <strong>知识库管理</strong>
          <Tag color="gold">仅管理员</Tag>
        </Space>
        <span>{user?.username}</span>
      </Header>
      <Content style={{ padding: 24, overflow: 'auto' }}>
        <Row gutter={16} style={{ marginBottom: 20 }}>
          <Col span={8}>
            <Card>
              <Statistic
                title="文档总数" value={stats?.document_count ?? 0}
                prefix={<FileTextOutlined />}
              />
            </Card>
          </Col>
          <Col span={8}>
            <Card>
              <Statistic
                title="向量总数" value={stats?.vector_count ?? 0}
                prefix={<DatabaseOutlined />}
              />
            </Card>
          </Col>
          <Col span={8}>
            <Card>
              <Statistic title="向量集合" value={stats?.collection ?? '-'} valueStyle={{ fontSize: 18 }} />
            </Card>
          </Col>
        </Row>

        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
          <Title level={4} style={{ margin: 0 }}>文档列表</Title>
          <Space>
            <Button icon={<ExperimentOutlined />} onClick={() => setPreviewOpen(true)}>
              分段预览调参
            </Button>
            <Button icon={<ReloadOutlined />} onClick={refresh}>刷新</Button>
            <Button type="primary" icon={<UploadOutlined />} onClick={() => setUploadOpen(true)}>
              上传文档
            </Button>
          </Space>
        </div>

        <Table
          rowKey="id" columns={columns} dataSource={docs} loading={loading}
          pagination={{ pageSize: 10 }}
        />
      </Content>

      {/* 上传对话框 */}
      <Modal
        title="上传知识库文档" open={uploadOpen} onOk={onUpload}
        confirmLoading={uploading} okText="上传并入库"
        onCancel={() => { setUploadOpen(false); setUploadFile(null) }}
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div>
            <Text type="secondary">分类（选自动分类则按篇名智能归类）</Text>
            <Select
              style={{ width: '100%', marginTop: 4 }} value={uploadType}
              onChange={setUploadType}
              options={DOC_TYPES.map((t) => ({ label: t, value: t }))}
            />
          </div>
          <Upload.Dragger
            maxCount={1} beforeUpload={(f) => { setUploadFile(f); return false }}
            onRemove={() => setUploadFile(null)}
            fileList={uploadFile ? [uploadFile] : []}
            accept=".pdf,.docx,.txt,.md,.csv,.xlsx"
          >
            <p className="ant-upload-drag-icon"><InboxOutlined /></p>
            <p>点击或拖拽文件到此处上传</p>
            <p style={{ color: '#999', fontSize: 12 }}>支持 pdf / docx / txt / md / csv / xlsx</p>
          </Upload.Dragger>
        </Space>
      </Modal>

      {/* 分段预览调参对话框 */}
      <Modal
        title="分段预览调参" open={previewOpen} width={720} footer={null}
        onCancel={() => setPreviewOpen(false)}
      >
        <Paragraph type="secondary">
          粘贴一段文本，调整参数查看切分效果，用于对比实验和参数调优。
        </Paragraph>
        <Input.TextArea
          value={previewText} onChange={(e) => setPreviewText(e.target.value)}
          placeholder="粘贴待分段的文本…" autoSize={{ minRows: 4, maxRows: 8 }}
        />
        <Space style={{ margin: '12px 0' }}>
          <span>块大小(100-2000)</span>
          <Input
            type="number" min={100} max={2000} style={{ width: 110 }} value={chunkSize}
            onChange={(e) => setChunkSize(Number(e.target.value))}
          />
          <span>重叠(0-500)</span>
          <Input
            type="number" min={0} max={500} style={{ width: 110 }} value={chunkOverlap}
            onChange={(e) => setChunkOverlap(Number(e.target.value))}
          />
          <Button type="primary" loading={previewing} onClick={onPreview}>预览分段</Button>
        </Space>
        {previewResult.length > 0 && (
          <div style={{ maxHeight: 320, overflow: 'auto' }}>
            <Text type="secondary">共 {previewResult.length} 段</Text>
            {previewResult.map((c) => (
              <Card key={c.index} size="small" style={{ marginTop: 8 }}
                title={<Text style={{ fontSize: 12 }}>#{c.index} · {c.length} 字</Text>}>
                <Text style={{ fontSize: 13, whiteSpace: 'pre-wrap' }}>{c.content}</Text>
              </Card>
            ))}
          </div>
        )}
      </Modal>
    </Layout>
  )
}
