-- Holocron Archive SQL Query Examples
-- 본 파일은 Holocron Archive 서비스에서 사용하는 대표 SQL 질의문을 정리한 파일이다.
-- 실제 테이블 생성 SQL은 schema.sql에 작성되어 있다.

-- 1. 특정 프랜차이즈의 전체 기사 최신순 조회
SELECT
    article_id,
    title,
    title_ko,
    source_name,
    source_url,
    image_url,
    published_at,
    summary,
    summary_ko,
    category,
    franchise
FROM articles
WHERE franchise = 'Star Wars'
ORDER BY published_at DESC;


-- 2. 특정 프랜차이즈의 특정 카테고리 기사 조회
SELECT
    article_id,
    title_ko,
    source_name,
    published_at,
    summary_ko,
    category,
    source_url,
    image_url
FROM articles
WHERE franchise = 'Star Wars'
  AND category = '게임'
ORDER BY published_at DESC;


-- 3. 키워드 검색
-- 제목, 한국어 제목, 요약, 한국어 요약, 출처명에서 특정 키워드가 포함된 기사 검색
SELECT
    article_id,
    title,
    title_ko,
    source_name,
    published_at,
    summary_ko,
    category,
    source_url,
    image_url
FROM articles
WHERE franchise = 'Star Wars'
  AND (
        title ILIKE '%Mandalorian%'
        OR title_ko ILIKE '%Mandalorian%'
        OR summary ILIKE '%Mandalorian%'
        OR summary_ko ILIKE '%Mandalorian%'
        OR source_name ILIKE '%Mandalorian%'
  )
ORDER BY published_at DESC;


-- 4. 기사 카테고리 목록 조회
SELECT DISTINCT category
FROM articles
WHERE franchise = 'Star Wars'
  AND category IS NOT NULL
ORDER BY category;


-- 5. 특정 프랜차이즈의 전체 작품 목록 최신순 조회
SELECT
    work_id,
    title,
    type,
    release_date,
    status,
    description,
    source_url,
    image_url,
    franchise
FROM works
WHERE franchise = 'Star Wars'
ORDER BY release_date DESC;


-- 6. 공개 예정 작품 조회
SELECT
    work_id,
    title,
    type,
    release_date,
    status,
    description,
    source_url,
    image_url,
    franchise
FROM works
WHERE franchise = 'Star Wars'
  AND status = 'Upcoming'
ORDER BY release_date ASC;


-- 7. 작품 유형별 개수 조회
SELECT
    franchise,
    type,
    COUNT(*) AS work_count
FROM works
GROUP BY franchise, type
ORDER BY franchise, work_count DESC;


-- 8. 기사 카테고리별 개수 조회
SELECT
    franchise,
    category,
    COUNT(*) AS article_count
FROM articles
GROUP BY franchise, category
ORDER BY franchise, article_count DESC;


-- 9. View 생성: 프랜차이즈별 기사 카테고리 통계
CREATE OR REPLACE VIEW article_category_stats AS
SELECT
    franchise,
    category,
    COUNT(*) AS article_count
FROM articles
GROUP BY franchise, category;


-- 10. View 조회
SELECT
    franchise,
    category,
    article_count
FROM article_category_stats
ORDER BY franchise, article_count DESC;


-- 11. 특정 사용자의 북마크 기사 조회
SELECT
    b.bookmark_id,
    u.username,
    a.title_ko,
    a.source_name,
    a.published_at,
    a.source_url
FROM bookmarks b
JOIN users u ON b.user_id = u.user_id
JOIN articles a ON b.article_id = a.article_id
WHERE u.username = 'test_user'
ORDER BY b.created_at DESC;


-- 12. 특정 사용자의 메모 조회
SELECT
    n.note_id,
    u.username,
    a.title_ko,
    n.note_text,
    n.created_at
FROM notes n
JOIN users u ON n.user_id = u.user_id
JOIN articles a ON n.article_id = a.article_id
WHERE u.username = 'test_user'
ORDER BY n.created_at DESC;


-- 13. 특정 작품과 관련된 기사 조회
SELECT
    w.title AS work_title,
    a.title_ko AS article_title,
    a.source_name,
    a.published_at,
    a.source_url
FROM work_articles wa
JOIN works w ON wa.work_id = w.work_id
JOIN articles a ON wa.article_id = a.article_id
WHERE w.franchise = 'Star Wars'
ORDER BY w.title, a.published_at DESC;


-- 14. 태그별 기사 조회
SELECT
    t.tag_name,
    a.title_ko,
    a.source_name,
    a.published_at,
    a.source_url
FROM article_tags at
JOIN tags t ON at.tag_id = t.tag_id
JOIN articles a ON at.article_id = a.article_id
ORDER BY t.tag_name, a.published_at DESC;


-- 15. 테이블별 Tuple 수 확인
SELECT 'users' AS table_name, COUNT(*) AS tuple_count FROM users
UNION ALL
SELECT 'works', COUNT(*) FROM works
UNION ALL
SELECT 'articles', COUNT(*) FROM articles
UNION ALL
SELECT 'work_articles', COUNT(*) FROM work_articles
UNION ALL
SELECT 'tags', COUNT(*) FROM tags
UNION ALL
SELECT 'article_tags', COUNT(*) FROM article_tags
UNION ALL
SELECT 'bookmarks', COUNT(*) FROM bookmarks
UNION ALL
SELECT 'notes', COUNT(*) FROM notes;

-- 16. 작품명 기반 관련 소식 검색
-- 작품 정보 페이지의 '관련 소식' 버튼과 연결되는 검색 기능
SELECT
    article_id,
    title,
    title_ko,
    source_name,
    published_at,
    summary_ko,
    category,
    source_url,
    image_url
FROM articles
WHERE franchise = 'Star Wars'
  AND (
        title ILIKE '%Mandalorian%'
        OR title_ko ILIKE '%Mandalorian%'
        OR summary ILIKE '%Mandalorian%'
        OR summary_ko ILIKE '%Mandalorian%'
  )
ORDER BY published_at DESC;


-- 17. 현재 상영/대표 작품 조회
-- 프로토타입에서는 The Mandalorian and Grogu를 극장 예매 대상 대표 작품으로 사용
SELECT
    work_id,
    title,
    type,
    release_date,
    status,
    description,
    source_url,
    image_url,
    franchise
FROM works
WHERE franchise = 'Star Wars'
  AND title = 'Star Wars: The Mandalorian and Grogu';