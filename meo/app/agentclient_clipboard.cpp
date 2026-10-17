#include "agentclient.h"

#include <QClipboard>
#include <QFileInfo>
#include <QGuiApplication>
#include <QMimeData>

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
