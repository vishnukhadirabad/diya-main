using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Avalonia.Media.Imaging;
using PDFtoImage;
using SkiaSharp;

namespace DiyaMeditation.Services;

/// <summary>
/// Locates and renders the meditation report PDF written by the external
/// meditation-app. The report directory defaults to /opt/meditation-app/data and
/// is overridable via DIYA_REPORT_DIR. Pages are rendered to Avalonia bitmaps so
/// the report can be shown inside the kiosk (no external viewer).
/// </summary>
public static class ReportRenderer
{
    public static string ReportDir =>
        Environment.GetEnvironmentVariable("DIYA_REPORT_DIR") is { Length: > 0 } d
            ? d
            : "/opt/meditation-app/data";

    /// <summary>Newest *.pdf in the report directory, or null if none/unreadable.</summary>
    public static string? FindNewestPdf()
    {
        try
        {
            var dir = ReportDir;
            if (!Directory.Exists(dir)) return null;
            return new DirectoryInfo(dir)
                .EnumerateFiles("*.pdf", SearchOption.TopDirectoryOnly)
                .OrderByDescending(f => f.LastWriteTimeUtc)
                .FirstOrDefault()?.FullName;
        }
        catch
        {
            return null;
        }
    }

    /// <summary>
    /// Rename a freshly generated report after the recognised visitor, e.g.
    /// "VISHNUKUMAR_Report_2026-08-18_1430.pdf". The meditation-app's t3 always
    /// writes the same generic filename, so without this every visitor's report
    /// overwrites the last and the file says nothing about whose it is. The
    /// timestamp keeps two sessions by the same person from colliding.
    /// Returns the new path, or the original path unchanged if the rename is
    /// not possible (bad name, permissions) — showing the report under its
    /// generic name beats not showing it at all.
    /// </summary>
    public static string RenameForVisitor(string pdfPath, string visitorName)
    {
        try
        {
            // Keep letters/digits/-/_ from the name; collapse everything else
            // (spaces, slashes, dots) to '_' so the result is filesystem-safe.
            var safe = new string(visitorName.Trim()
                .Select(c => char.IsLetterOrDigit(c) || c is '-' or '_' ? c : '_')
                .ToArray()).Trim('_');
            if (safe.Length == 0) return pdfPath;

            var dir = Path.GetDirectoryName(pdfPath) ?? ReportDir;
            var dest = Path.Combine(dir, $"{safe}_Report_{DateTime.Now:yyyy-MM-dd_HHmm}.pdf");
            if (dest == pdfPath) return pdfPath;

            File.Move(pdfPath, dest, overwrite: true);
            Console.WriteLine($"[report] renamed for visitor: {Path.GetFileName(pdfPath)} -> {Path.GetFileName(dest)}");
            return dest;
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[report] rename failed ({ex.Message}) — keeping {pdfPath}");
            return pdfPath;
        }
    }

    /// <summary>
    /// Render every page of the PDF to Avalonia bitmaps. Runs off the UI thread.
    /// </summary>
    public static Task<List<Bitmap>> RenderPagesAsync(string pdfPath) => Task.Run(() =>
    {
        var pages = new List<Bitmap>();
        var bytes = File.ReadAllBytes(pdfPath);
        using var input = new MemoryStream(bytes);

        foreach (var sk in Conversion.ToImages(input))
        {
            using (sk)
            using (var img = SKImage.FromBitmap(sk))
            using (var data = img.Encode(SKEncodedImageFormat.Png, 90))
            {
                var ms = new MemoryStream();
                data.SaveTo(ms);
                ms.Position = 0;
                pages.Add(new Bitmap(ms));
            }
        }

        return pages;
    });
}
