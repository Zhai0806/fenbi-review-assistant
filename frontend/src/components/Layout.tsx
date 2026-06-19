import { Layout, Menu, Button } from "antd";
import {
  DashboardOutlined,
  FileTextOutlined,
  BookOutlined,
  BarChartOutlined,
  RobotOutlined,
  FormOutlined,
  EditOutlined,
  MoonOutlined,
  SunOutlined,
} from "@ant-design/icons";
import { useNavigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

const { Sider, Content, Header } = Layout;

const menuItems = [
  { key: "/", icon: <DashboardOutlined />, label: "仪表盘" },
  { key: "/exam/1", icon: <FileTextOutlined />, label: "模考复盘" },
  { key: "/wrong-bank", icon: <BookOutlined />, label: "错题本" },
  { key: "/insights", icon: <BarChartOutlined />, label: "知识洞察" },
  { key: "/chat", icon: <RobotOutlined />, label: "AI 顾问" },
  { key: "/shenlun", icon: <EditOutlined />, label: "申论" },
  { key: "/notes", icon: <FormOutlined />, label: "笔记链接" },
];

export default function AppLayout({
  children,
  dark,
  onToggleDark,
}: {
  children: ReactNode;
  dark: boolean;
  onToggleDark: () => void;
}) {
  const nav = useNavigate();
  const loc = useLocation();

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider breakpoint="lg" collapsedWidth="60" width={180}>
        <div style={{ color: "#1a73e8", fontSize: 16, fontWeight: 700, padding: "12px 16px" }}>📝 粉笔复盘</div>
        <Menu mode="inline" selectedKeys={[loc.pathname]} items={menuItems} onClick={({ key }) => nav(key)} />
      </Sider>
      <Layout>
        <Content style={{ margin: 0, padding: "12px 16px", fontSize: 15 }}>
          {children}
        </Content>
      </Layout>
    </Layout>
  );
}
