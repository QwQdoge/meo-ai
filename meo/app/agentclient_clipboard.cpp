#include "agentclient.h"

#include <QClipboard>
#include <QCoreApplication>
#include <QFileInfo>
#include <QGuiApplication>
#include <QMimeData>
#include <QStringList>
#include <QSysInfo>

int AgentClient::addClipboardResources() {
    if (!m_serviceMode || busy() || actionBusy()) {
        m_status = tr("Clipboard attachment is only available in idle AgentService mode.");
        emit changed();
        return 0;
    }

    QClipboard *clipboard = QGuiApplication::clipboard();
    const QMimeData *mime = clipboard ? clipboard->mimeData() : nullptr;
    if (!mime) {
        m_status = tr("Clipboard is empty.");
        emit changed();
        return 0;
    }

    int attachedFiles = 0;
    if (mime->hasUrls()) {
        for (const QUrl &url : mime->urls()) {
            if (!url.isLocalFile())
                continue;
            const QFileInfo info(url.toLocalFile());
            if (!info.exists() || !info.isFile())
                continue;
            addFileResource(url);
            ++attachedFiles;
        }
        if (attachedFiles > 0)
            return attachedFiles;
    }

    if (mime->hasImage())
        return addClipboardImageResource() ? 1 : 0;

    m_status = tr("Clipboard does not contain local files or an image.");
    emit changed();
    return 0;
}

void AgentClient::copyDiagnosticsToClipboard() {
    QClipboard *clipboard = QGuiApplication::clipboard();
    if (!clipboard) {
        m_status = tr("Clipboard is unavailable.");
        emit changed();
        return;
    }

    QString version = QCoreApplication::applicationVersion().trimmed();
    if (version.isEmpty())
        version = QStringLiteral("development");

    QString selectedModel;
    for (const QVariant &value : m_models) {
        const QVariantMap model = value.toMap();
        if (model.value(QStringLiteral("selected")).toBool()) {
            selectedModel = model.value(QStringLiteral("label")).toString().trimmed();
            if (selectedModel.isEmpty())
                selectedModel = tr("Selected model");
            break;
        }
    }
    if (selectedModel.isEmpty())
        selectedModel = tr("Not selected");

    const bool requestActive = busy() || actionBusy() || !m_options.isEmpty();
    const QString platform = QSysInfo::prettyProductName().trimmed().isEmpty()
        ? QSysInfo::productType()
        : QSysInfo::prettyProductName().trimmed();

    const QStringList lines{
        QStringLiteral("Meo AI %1").arg(version),
        QStringLiteral("Platform: %1 (%2)").arg(platform, QSysInfo::currentCpuArchitecture()),
        QStringLiteral("Qt: %1").arg(QString::fromLatin1(qVersion())),
        QStringLiteral("Transport: %1").arg(m_serviceMode
            ? QStringLiteral("Local AgentService")
            : QStringLiteral("Legacy local API")),
        QStringLiteral("AgentService ready: %1").arg(m_agentState.value(QStringLiteral("ready")).toBool()
            ? QStringLiteral("yes") : QStringLiteral("no")),
        QStringLiteral("Status: %1").arg(m_status.trimmed().isEmpty()
            ? QStringLiteral("unknown") : m_status.trimmed()),
        QStringLiteral("Metadata: %1").arg(m_metadataStatus.trimmed().isEmpty()
            ? QStringLiteral("unknown") : m_metadataStatus.trimmed()),
        QStringLiteral("Selected model: %1").arg(selectedModel),
        QStringLiteral("Request active: %1").arg(requestActive ? QStringLiteral("yes") : QStringLiteral("no")),
        QStringLiteral("Pending attachments: %1").arg(m_pendingResources.size()),
    };

    clipboard->setText(lines.join(QLatin1Char('\n')), QClipboard::Clipboard);
    m_status = tr("Diagnostics copied");
    emit changed();
}
