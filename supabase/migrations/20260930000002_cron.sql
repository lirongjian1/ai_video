-- ============================================================
-- 定时轮询视频任务：用 pg_cron + pg_net 定期调用 ai-video-poll
--
-- 依赖 20260930000004_app_config.sql 创建的 app_config 表，
-- 请先执行下面的 insert 填好两项配置，再执行本文件：
--
--   insert into public.app_config (key, value) values
--     ('supabase_url', 'https://xxxxx.supabase.co'),
--     ('cron_secret',  '你的随机串（需与 Edge Function CRON_SECRET 一致）')
--   on conflict (key) do update set value = excluded.value, updated_at = now();
--
-- 注意：不要用 alter database set app.settings.*，
-- 托管实例会报 42501 permission denied。
-- ============================================================

create extension if not exists pg_cron with schema extensions;
create extension if not exists pg_net with schema extensions;

-- 每 15 秒轮询一次待处理视频任务
select cron.unschedule('poll-video-tasks')
where exists (select 1 from cron.job where jobname = 'poll-video-tasks');

select cron.schedule(
  'poll-video-tasks',
  '15 seconds',
  $$
  select net.http_post(
    url := public.app_config_get('supabase_url') || '/functions/v1/ai-video-poll',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'x-cron-secret', public.app_config_get('cron_secret')
    ),
    body := '{}'::jsonb
  );
  $$
);
