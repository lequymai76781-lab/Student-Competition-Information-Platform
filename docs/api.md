# API 说明

所有 API 使用统一响应结构：

```json
{
  "success": true,
  "data": {},
  "message": "ok",
  "meta": null
}
```

已实现接口：

- `GET /api/health`
- `GET /api/competitions`
- `GET /api/competitions/{id}`
- `POST /api/competitions`
- `PUT /api/competitions/{id}`
- `GET /api/competition/{id}/university-recognition`
- `GET /api/universities`
- `GET /api/universities/{id}`
- `GET /api/universities/{id}/policies`
- `GET /api/universities/{id}/competition-policies`
- `POST /api/recommendations`
- `GET /api/tags`
- `GET /api/stats`

推荐接口示例：

```bash
curl -X POST http://localhost:8000/api/recommendations \
  -H "Content-Type: application/json" \
  -d "{\"university_id\":1,\"major_name\":\"播音与主持艺术\",\"grade\":\"大二\",\"goal\":\"保研\",\"skills\":[\"AIGC\",\"视频制作\"],\"interest_tags\":[\"新闻传播\",\"广告设计\"],\"weekly_available_hours\":8,\"accept_cross_major\":true,\"accept_cross_university\":true,\"limit\":5}"
```

