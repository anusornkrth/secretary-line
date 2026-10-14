-- รันใน Supabase SQL Editor

-- ข้อความทั้งหมด (ใช้สรุปแชท)
create table messages (
  id          bigserial primary key,
  chat_id     text not null,          -- groupId หรือ userId
  user_id     text,
  text        text,
  created_at  timestamptz default now()
);
create index on messages (chat_id, created_at);

-- ประวัติบทสนทนากับบอท (ความจำระยะสั้น)
create table conversations (
  id          bigserial primary key,
  chat_id     text not null,
  role        text not null,          -- 'user' | 'assistant'
  content     text not null,
  created_at  timestamptz default now()
);
create index on conversations (chat_id, created_at);

-- งาน / To-do
create table tasks (
  id          bigserial primary key,
  chat_id     text not null,
  title       text not null,
  owner       text,
  due_date    date,
  status      text default 'todo',    -- 'todo' | 'done'
  created_at  timestamptz default now()
);

-- รายชื่อห้องที่ต้องการสรุปรายวัน
create table subscriptions (
  chat_id     text primary key,
  created_at  timestamptz default now()
);
