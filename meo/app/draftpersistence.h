#pragma once

#include <QObject>
#include <QPointer>
#include <QTimer>

class DraftPersistence final : public QObject {
    Q_OBJECT

public:
    explicit DraftPersistence(QObject *parent = nullptr);

    bool attach(QObject *composer);
    Q_INVOKABLE void flush();

private slots:
    void onTextChanged();

private:
    QString currentText() const;
    void clearStoredDraft();

    QPointer<QObject> m_composer;
    QTimer m_debounce;
};
