import { useEffect } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { Spin } from 'antd'
import { useAuthStore } from '@/store/auth'

interface Props {
  children: React.ReactNode
  requireAdmin?: boolean
}

/** 路由守卫：未登录跳登录；requireAdmin 时非管理员跳问答页。 */
export default function RequireAuth({ children, requireAdmin }: Props) {
  const location = useLocation()
  const { token, user, loading, fetchMe } = useAuthStore()

  useEffect(() => {
    if (token && !user) {
      fetchMe()
    }
  }, [token, user, fetchMe])

  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (!user || loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 120 }}>
        <Spin size="large" />
      </div>
    )
  }

  if (requireAdmin && user.role !== 'admin') {
    return <Navigate to="/chat" replace />
  }

  return <>{children}</>
}
