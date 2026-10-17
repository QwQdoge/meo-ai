#include "draftpersistence.h"

#include <QMetaProperty>
#include <QQmlProperty>
#include <QSettings>

namespace {
constexpr auto kDraftGroup = "NativeDraft";
constexpr auto kDraftKey = "composerText";
constexpr int kDraftDebounceMs = 300;
}

DraftPersistence::DraftPersistence(QObject *parent)
    : QObject(parent)
{
    m_debounce.setSingleShot(true);
    m_debounce.setInterval(kDraftDebounceMs);
    connect(&m_debounce, &QTimer::timeout, this, &DraftPersistence::flush);
}

bool DraftPersistence::attach(QObject *composer)
{
    if (!composer || m_composer)
        return false;

    const int propertyIndex = composer->metaObject()->indexOfProperty("text");
    if (propertyIndex < 0)
        return false;
    const QMetaProperty metaProperty = composer->metaObject()->property(propertyIndex);
    if (!metaProperty.isWritable() || !metaProperty.hasNotifySignal())
        return false;

    QQmlProperty textProperty(composer, QStringLiteral("text"));
    if (!textProperty.isValid() || !textProperty.isWritable())
        return false;

    m_composer = composer;

    QSettings settings;
    settings.beginGroup(QStringLiteral(kDraftGroup));
    const QString storedDraft = settings.value(QStringLiteral(kDraftKey)).toString();
    settings.endGroup();

    if (textProperty.read().toString().isEmpty() && !storedDraft.isEmpty())
        textProperty.write(storedDraft);

    if (!textProperty.connectNotifySignal(this, SLOT(onTextChanged()))) {
        m_composer.clear();
        return false;
    }

    connect(composer, &QObject::destroyed, this, [this] {
        m_debounce.stop();
        m_composer.clear();
    });
    return true;
}

QString DraftPersistence::currentText() const
{
    if (!m_composer)
        return {};
    return QQmlProperty(m_composer, QStringLiteral("text")).read().toString();
}

void DraftPersistence::clearStoredDraft()
{
    QSettings settings;
    settings.beginGroup(QStringLiteral(kDraftGroup));
    settings.remove(QStringLiteral(kDraftKey));
    settings.endGroup();
    settings.sync();
}

void DraftPersistence::onTextChanged()
{
    if (!m_composer)
        return;

    if (currentText().isEmpty()) {
        m_debounce.stop();
        clearStoredDraft();
        return;
    }
    m_debounce.start();
}

void DraftPersistence::flush()
{
    if (!m_composer)
        return;

    const QString text = currentText();
    if (text.isEmpty()) {
        clearStoredDraft();
        return;
    }

    QSettings settings;
    settings.beginGroup(QStringLiteral(kDraftGroup));
    settings.setValue(QStringLiteral(kDraftKey), text);
    settings.endGroup();
    settings.sync();
}
