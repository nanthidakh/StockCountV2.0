<%@ WebHandler Language="C#" Class="ExportHandler" %>
using System;
using System.Web;
using System.Data;
using System.Data.SqlClient;
using System.IO;
using System.Collections;
using System.Collections.Generic;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;

public class ExportHandler : IHttpHandler
{
    public void ProcessRequest(HttpContext context)
    {
        context.Response.ContentType = "application/json";
        context.Response.ContentEncoding = System.Text.Encoding.UTF8;

        JavaScriptSerializer serializer = new JavaScriptSerializer();

        if (!String.Equals(context.Request.HttpMethod, "POST", StringComparison.OrdinalIgnoreCase))
        {
            WriteJson(context, serializer, 405, false, "Method Not Allowed", 0);
            return;
        }

        try
        {
            string jsonString;
            using (StreamReader reader = new StreamReader(context.Request.InputStream))
            {
                jsonString = reader.ReadToEnd();
            }

            Dictionary<string, object> data =
                serializer.Deserialize<Dictionary<string, object>>(jsonString);

            if (data == null)
            {
                throw new Exception("ไม่พบข้อมูล Request");
            }

            string dbServer = GetRequiredString(data, "db_server_ip");
            string dbName = GetRequiredString(data, "db_name");
            string action = GetOptionalString(data, "action", "export");

            string connString = String.Format(
                "Server={0};Database={1};User Id=sa;Password=Hwkingp@ss;Connection Timeout=10;",
                dbServer,
                dbName
            );

            using (SqlConnection conn = new SqlConnection(connString))
            {
                conn.Open();

                if (String.Equals(action, "test_connection", StringComparison.OrdinalIgnoreCase))
                {
                    WriteJson(context, serializer, 200, true, "เชื่อมต่อฐานข้อมูลสำเร็จ", 0);
                    return;
                }

                string tableName = GetRequiredString(data, "table");
                ValidateTableName(tableName);

                if (!data.ContainsKey("data") || !(data["data"] is ArrayList))
                {
                    throw new Exception("รูปแบบ data ไม่ถูกต้อง");
                }

                ArrayList rows = (ArrayList)data["data"];
                int insertedCount = 0;

                using (SqlTransaction transaction = conn.BeginTransaction())
                {
                    try
                    {
                        string sql =
                            "INSERT INTO [" + tableName + "] " +
                            "([location], [staff_name], [product_code], [barcode], [qty], [scan_date], [export_date]) " +
                            "VALUES (@loc, @staff, @code, @bar, @qty, @date, GETDATE())";

                        foreach (object item in rows)
                        {
                            Dictionary<string, object> row =
                                item as Dictionary<string, object>;

                            if (row == null)
                            {
                                throw new Exception("พบรายการข้อมูลที่มีรูปแบบไม่ถูกต้อง");
                            }

                            using (SqlCommand cmd = new SqlCommand(sql, conn, transaction))
                            {
                                cmd.Parameters.Add("@loc", SqlDbType.NVarChar, 100).Value =
                                    GetRequiredString(row, "location");

                                cmd.Parameters.Add("@staff", SqlDbType.NVarChar, 100).Value =
                                    GetRequiredString(row, "staff");

                                cmd.Parameters.Add("@code", SqlDbType.NVarChar, 100).Value =
                                    GetRequiredString(row, "p_code");

                                cmd.Parameters.Add("@bar", SqlDbType.NVarChar, 100).Value =
                                    GetOptionalString(row, "barcode", "");

                                cmd.Parameters.Add("@qty", SqlDbType.Decimal).Value =
                                    GetRequiredDecimal(row, "qty");

                                cmd.Parameters.Add("@date", SqlDbType.DateTime).Value =
                                    GetRequiredDateTime(row, "date");

                                cmd.ExecuteNonQuery();
                                insertedCount++;
                            }
                        }

                        transaction.Commit();
                    }
                    catch
                    {
                        transaction.Rollback();
                        throw;
                    }
                }

                WriteJson(
                    context,
                    serializer,
                    200,
                    true,
                    "ส่งออกข้อมูลสำเร็จ",
                    insertedCount
                );
            }
        }
        catch (Exception ex)
        {
            // ระหว่างทดสอบส่งรายละเอียดกลับไปเพื่อให้ App แสดงสาเหตุจริง
            WriteJson(context, serializer, 500, false, ex.ToString(), 0);
        }
    }

    private static string GetRequiredString(
        Dictionary<string, object> source,
        string key
    )
    {
        if (!source.ContainsKey(key) || source[key] == null)
        {
            throw new Exception("ไม่พบค่า " + key);
        }

        string value = source[key].ToString().Trim();
        if (value.Length == 0)
        {
            throw new Exception("ค่า " + key + " ว่าง");
        }

        return value;
    }

    private static string GetOptionalString(
        Dictionary<string, object> source,
        string key,
        string defaultValue
    )
    {
        if (!source.ContainsKey(key) || source[key] == null)
        {
            return defaultValue;
        }

        return source[key].ToString().Trim();
    }

    private static decimal GetRequiredDecimal(
        Dictionary<string, object> source,
        string key
    )
    {
        string value = GetRequiredString(source, key);
        decimal result;

        if (!Decimal.TryParse(value, out result))
        {
            throw new Exception("ค่า " + key + " ไม่ใช่ตัวเลข: " + value);
        }

        return result;
    }

    private static DateTime GetRequiredDateTime(
        Dictionary<string, object> source,
        string key
    )
    {
        string value = GetRequiredString(source, key);
        DateTime result;

        if (!DateTime.TryParse(value, out result))
        {
            throw new Exception("ค่า " + key + " ไม่ใช่วันที่: " + value);
        }

        return result;
    }

    private static void ValidateTableName(string tableName)
    {
        // อนุญาตเฉพาะชื่อตารางธรรมดา ป้องกันการต่อ SQL จากค่าที่ส่งเข้ามา
        if (!Regex.IsMatch(tableName, @"^[A-Za-z0-9_]+$"))
        {
            throw new Exception("ชื่อตารางไม่ถูกต้อง: " + tableName);
        }
    }

    private static void WriteJson(
        HttpContext context,
        JavaScriptSerializer serializer,
        int statusCode,
        bool success,
        string message,
        int count
    )
    {
        context.Response.StatusCode = statusCode;
        context.Response.TrySkipIisCustomErrors = true;
        context.Response.Write(
            serializer.Serialize(
                new
                {
                    success = success,
                    message = message,
                    count = count
                }
            )
        );
    }

    public bool IsReusable
    {
        get { return false; }
    }
}
