-- 계열사 시드. schema.sql 다음에 실행한다: mysql -u root -p spaceh < db/seed.sql
-- 시드 계정은 비밀번호 해시가 필요해서 SQL이 아니라 scripts/seed_users.py로 넣는다.
-- dart_code는 I-05 시작 전에 DART 고유번호를 확인해 채운다.

INSERT INTO companies (company_id, name, dart_code) VALUES
  ('HRI', '현대경제연구원', NULL),
  ('MVX', '현대무벡스', NULL),
  ('ELV', '현대엘리베이터', NULL);
