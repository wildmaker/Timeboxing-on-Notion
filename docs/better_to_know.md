
# 外部数据源的数据结构

## notion_api.get_database(database_id)
{
  "object": "database",
  "id": "197e2dff-a69e-80b7-941c-f956f765560b",
  "cover": null,
  "icon": {
    "type": "external",
    "external": {
      "url": "https://www.notion.so/icons/clock_red.svg"
    }
  },
  "created_time": "2025-02-11T09:13:00.000Z",
  "created_by": {
    "object": "user",
    "id": "0c9b2448-533a-4ef3-b9b7-224adb1e750b"
  },
  "last_edited_by": {
    "object": "user",
    "id": "0c9b2448-533a-4ef3-b9b7-224adb1e750b"
  },
  "last_edited_time": "2025-06-06T07:50:00.000Z",
  "title": [
    {
      "type": "text",
      "text": {
        "content": "Time Boxing",
        "link": null
      },
      "annotations": {
        "bold": false,
        "italic": false,
        "strikethrough": false,
        "underline": false,
        "code": false,
        "color": "default"
      },
      "plain_text": "Time Boxing",
      "href": null
    }
  ],
  "description": [],
  "is_inline": false,
  "properties": {
    "用户价值": {
      "id": "%3AtBR",
      "name": "用户价值",
      "type": "rich_text",
      "rich_text": {}
    },
    "子级 项目": {
      "id": "%3BHQg",
      "name": "子级 项目",
      "type": "relation",
      "relation": {
        "database_id": "197e2dff-a69e-80b7-941c-f956f765560b",
        "type": "dual_property",
        "dual_property": {
          "synced_property_name": "上级 项目",
          "synced_property_id": "%60cfb"
        }
      }
    },
    "Last edited time": {
      "id": "B%3Dkf",
      "name": "Last edited time",
      "type": "last_edited_time",
      "last_edited_time": {}
    },
    "季度": {
      "id": "Gpwd",
      "name": "季度",
      "type": "multi_select",
      "multi_select": {
        "options": [
          {
            "id": "zY?P",
            "name": "Q1",
            "color": "default",
            "description": null
          },
          {
            "id": "pBJL",
            "name": "Q2",
            "color": "orange",
            "description": null
          },
          {
            "id": "`N\\o",
            "name": "Q3",
            "color": "purple",
            "description": null
          },
          {
            "id": "yz~X",
            "name": "Q4",
            "color": "brown",
            "description": null
          }
        ]
      }
    },
    "DDL": {
      "id": "Qb%40%3C",
      "name": "DDL",
      "type": "formula",
      "formula": {
        "expression": "dateAdd({{notion:block_property:174acb8f-ef89-424f-976e-da3c1dd41801:00000000-0000-0000-0000-000000000000:df8fd115-e433-452b-8107-afd3e8efce75}},{{notion:block_property:hahR:00000000-0000-0000-0000-000000000000:df8fd115-e433-452b-8107-afd3e8efce75}},\"minutes\")"
      }
    },
    "正在阻止": {
      "id": "SuUu",
      "name": "正在阻止",
      "type": "relation",
      "relation": {
        "database_id": "197e2dff-a69e-80b7-941c-f956f765560b",
        "type": "dual_property",
        "dual_property": {
          "synced_property_name": "被阻止",
          "synced_property_id": "cmRW"
        }
      }
    },
    "状态": {
      "id": "U%3ANr",
      "name": "状态",
      "type": "status",
      "status": {
        "options": [
          {
            "id": "itFu",
            "name": "收件箱",
            "color": "default",
            "description": null
          },
          {
            "id": "\\Hz;",
            "name": "已计划",
            "color": "gray",
            "description": null
          },
          {
            "id": "{wjv",
            "name": "超出时间盒暂停",
            "color": "yellow",
            "description": null
          },
          {
            "id": "7e4f8156-5ddd-4637-bbf6-46e60884e5e2",
            "name": "进行中",
            "color": "blue",
            "description": null
          },
          {
            "id": "ddf25ae2-d666-4a55-a5cf-08d3592a3698",
            "name": "已完成",
            "color": "green",
            "description": null
          },
          {
            "id": "J@Gx",
            "name": "已取消",
            "color": "red",
            "description": null
          }
        ],
        "groups": [
          {
            "id": "7f59ecf1-28e6-4303-b259-869e464baf84",
            "name": "To-do",
            "color": "gray",
            "option_ids": ["itFu", "\\Hz;"]
          },
          {
            "id": "d355000c-1f57-4031-a296-6412cd11e1eb",
            "name": "In progress",
            "color": "blue",
            "option_ids": ["{wjv", "7e4f8156-5ddd-4637-bbf6-46e60884e5e2"]
          },
          {
            "id": "ba0eb40c-6466-45c5-b08a-48c98a95d742",
            "name": "Complete",
            "color": "green",
            "option_ids": ["ddf25ae2-d666-4a55-a5cf-08d3592a3698", "J@Gx"]
          }
        ]
      }
    },
    "上级 项目": {
      "id": "%60cfb",
      "name": "上级 项目",
      "type": "relation",
      "relation": {
        "database_id": "197e2dff-a69e-80b7-941c-f956f765560b",
        "type": "dual_property",
        "dual_property": {
          "synced_property_name": "子级 项目",
          "synced_property_id": "%3BHQg"
        }
      }
    },
    "类别": {
      "id": "b%5Bou",
      "name": "类别",
      "type": "multi_select",
      "multi_select": {
        "options": [
          {
            "id": "8c1b7486-cbc3-4275-8bb7-b155d4b5a1b9",
            "name": "功能",
            "color": "purple",
            "description": null
          },
          {
            "id": "b1190d14-bdbf-497a-afdc-3ed0e6e77185",
            "name": "增强",
            "color": "default",
            "description": null
          },
          {
            "id": "447798e6-3572-4d5d-98c6-81e45cce0a76",
            "name": "🐞 Bug",
            "color": "yellow",
            "description": null
          },
          {
            "id": "83218d48-7e7c-4c6d-8642-9e67435f4006",
            "name": "性能改进",
            "color": "orange",
            "description": null
          },
          {
            "id": "6f229123-3ea1-4c08-a4ae-8a6116f5377a",
            "name": "UI/UX",
            "color": "red",
            "description": null
          },
          {
            "id": "ac8fd2c6-fe3c-4601-a09e-d7998b459606",
            "name": "积极广告",
            "color": "pink",
            "description": null
          },
          {
            "id": "c8eb0a1b-5f2a-411c-abd4-e76abdb6759f",
            "name": "调研",
            "color": "gray",
            "description": null
          },
          {
            "id": "92a66740-9964-4d74-9585-93b97a436742",
            "name": "管理",
            "color": "brown",
            "description": null
          },
          {
            "id": "f3414d9a-1f36-4850-a7ee-ee6991d55787",
            "name": "需求",
            "color": "blue",
            "description": null
          },
          {
            "id": "8a09787f-0637-4bcb-81b9-cdb2243a8162",
            "name": "OKR",
            "color": "purple",
            "description": null
          }
        ]
      }
    },
    "优先级": {
      "id": "caT_",
      "name": "优先级",
      "type": "select",
      "select": {
        "options": [
          {
            "id": "rXuC",
            "name": "P0",
            "color": "red",
            "description": null
          },
          {
            "id": "viNr",
            "name": "P1",
            "color": "yellow",
            "description": null
          },
          {
            "id": "MRR`",
            "name": "P2",
            "color": "blue",
            "description": null
          },
          {
            "id": "Iey>",
            "name": "P3",
            "color": "green",
            "description": null
          },
          {
            "id": "543ea9f0-5388-45b0-9539-aff3219612f2",
            "name": "P4",
            "color": "default",
            "description": null
          }
        ]
      }
    },
    "被阻止": {
      "id": "cmRW",
      "name": "被阻止",
      "type": "relation",
      "relation": {
        "database_id": "197e2dff-a69e-80b7-941c-f956f765560b",
        "type": "dual_property",
        "dual_property": {
          "synced_property_name": "正在阻止",
          "synced_property_id": "SuUu"
        }
      }
    },
    "估计用时": {
      "id": "hahR",
      "name": "估计用时",
      "type": "number",
      "number": {
        "format": "number"
      }
    },
    "工作量": {
      "id": "nmCG",
      "name": "工作量",
      "type": "select",
      "select": {
        "options": [
          {
            "id": "G=S^",
            "name": "红色",
            "color": "red",
            "description": null
          },
          {
            "id": "cOb~",
            "name": "L",
            "color": "orange",
            "description": null
          },
          {
            "id": "=KTG",
            "name": "M",
            "color": "yellow",
            "description": null
          },
          {
            "id": "@CF=",
            "name": "S",
            "color": "blue",
            "description": null
          },
          {
            "id": "Tj:m",
            "name": "XS",
            "color": "green",
            "description": null
          }
        ]
      }
    },
    "版本": {
      "id": "pafe",
      "name": "版本",
      "type": "select",
      "select": {
        "options": [
          {
            "id": "c4b3e33a-c67b-41bd-bf99-136a9fa69d6e",
            "name": "v0.0.2",
            "color": "orange",
            "description": null
          },
          {
            "id": "1480b197-faac-4c18-9233-ad0ddae22230",
            "name": "v0.0.1",
            "color": "green",
            "description": null
          }
        ]
      }
    },
    "规划时间盒": {
      "id": "rrIH",
      "name": "规划时间盒",
      "type": "formula",
      "formula": {
        "expression": "dateRange({{notion:block_property:174acb8f-ef89-424f-976e-da3c1dd41801:00000000-0000-0000-0000-000000000000:df8fd115-e433-452b-8107-afd3e8efce75}},{{notion:block_property:Qb%40%3C:00000000-0000-0000-0000-000000000000:df8fd115-e433-452b-8107-afd3e8efce75}})"
      }
    },
    "所有者": {
      "id": "t%5Cqa",
      "name": "所有者",
      "type": "people",
      "people": {}
    },
    "Project": {
      "id": "~%3BJc",
      "name": "Project",
      "type": "select",
      "select": {
        "options": [
          {
            "id": "0a3e0b00-db17-4027-82e2-23f31dc44a89",
            "name": "Instant AI",
            "color": "pink",
            "description": null
          }
        ]
      }
    },
    "Story 名称": {
      "id": "title",
      "name": "Story 名称",
      "type": "title",
      "title": {}
    },
    "Time Box": {
      "id": "174acb8f-ef89-424f-976e-da3c1dd41801",
      "name": "Time Box",
      "type": "date",
      "date": {}
    },
    "前往滴答清单": {
      "id": "a5b39c47-9343-4e07-8e25-4f3c5259b076",
      "name": "前往滴答清单",
      "type": "rich_text",
      "rich_text": {}
    },
    "完成": {
      "id": "ae590bee-e2a3-4cfa-bf51-20a52c6871b6",
      "name": "完成",
      "type": "checkbox",
      "checkbox": {}
    },
    "标签": {
      "id": "cbff65cb-0e4b-40cb-a6ca-55ec2647c94d",
      "name": "标签",
      "type": "multi_select",
      "multi_select": {
        "options": [
          {
            "id": "793f66f9-fd23-46f0-bc4d-11591c26d264",
            "name": "敏捷上午🌞",
            "color": "gray",
            "description": null
          },
          {
            "id": "f25ec1f3-d56b-475e-bbd6-d4d3fa571f18",
            "name": "敏捷下午🌤",
            "color": "green",
            "description": null
          },
          {
            "id": "6c5354a0-38e8-4230-a1b4-79b1ce1a1970",
            "name": "晚饭后",
            "color": "purple",
            "description": null
          },
          {
            "id": "80950dfe-0631-4190-8346-efae729f34a5",
            "name": "早上🌅",
            "color": "blue",
            "description": null
          },
          {
            "id": "beddf6b6-9051-4049-9719-c9293d5f0b47",
            "name": "晚上",
            "color": "default",
            "description": null
          },
          {
            "id": "5e122227-1611-4676-823a-69765dfb1ee2",
            "name": "跨天项block其他",
            "color": "pink",
            "description": null
          },
          {
            "id": "ee69b1c3-aadb-4e7e-83bc-5568c4c92912",
            "name": "午饭后⛱️",
            "color": "orange",
            "description": null
          },
          {
            "id": "bb4a7939-796c-4288-b12b-0d22bb7e24f7",
            "name": "傍晚",
            "color": "red",
            "description": null
          }
        ]
      }
    }
  },
  "parent": {
    "type": "workspace",
    "workspace": true
  },
  "url": "https://www.notion.so/197e2dffa69e80b7941cf956f765560b",
  "public_url": null,
  "archived": false,
  "in_trash": false,
  "request_id": "63b08895-1a38-4a3b-a44d-412f8194bc65"
}