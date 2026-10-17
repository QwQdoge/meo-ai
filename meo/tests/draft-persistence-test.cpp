#include "draftpersistence.h"

#include <QSettings>
#include <QTest>

class DraftObject final : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString text READ text WRITE setText NOTIFY textChanged)

public:
    QString text() const { return m_text; }

    void setText(const QString &text) {
        if (m_text == text)
            return;
        m_text = text;
        emit textChanged();
    }

signals:
    void textChanged();

private:
    QString m_text;
};

class DraftPersistenceTest : public QObject {
    Q_OBJECT

private:
    static QString storedDraft() {
        QSettings settings;
        settings.beginGroup(QStringLiteral("NativeDraft"));
        const QString value = settings.value(QStringLiteral("composerText")).toString();
        settings.endGroup();
        return value;
    }

    static bool hasStoredDraft() {
        QSettings settings;
        settings.beginGroup(QStringLiteral("NativeDraft"));
        const bool present = settings.contains(QStringLiteral("composerText"));
        settings.endGroup();
        return present;
    }

    static void storeDraft(const QString &value) {
        QSettings settings;
        settings.beginGroup(QStringLiteral("NativeDraft"));
        settings.setValue(QStringLiteral("composerText"), value);
        settings.endGroup();
        settings.sync();
    }

private slots:
    void initTestCase() {
        QCoreApplication::setOrganizationName(QStringLiteral("MeoArchDraftPersistenceTest"));
        QCoreApplication::setApplicationName(QStringLiteral("MeoAIDraftPersistenceTest"));
    }

    void cleanup() {
        QSettings().clear();
    }

    void restoresStoredDraftAndPersistsChanges() {
        storeDraft(QStringLiteral("saved before restart"));

        DraftObject composer;
        DraftPersistence persistence;
        QVERIFY(persistence.attach(&composer));
        QCOMPARE(composer.text(), QStringLiteral("saved before restart"));

        composer.setText(QStringLiteral("updated draft"));
        QTRY_COMPARE_WITH_TIMEOUT(storedDraft(), QStringLiteral("updated draft"), 1500);

        composer.setText(QString());
        QTRY_VERIFY_WITH_TIMEOUT(!hasStoredDraft(), 500);
    }

    void existingComposerTextWinsOverOldStoredDraft() {
        storeDraft(QStringLiteral("older persisted value"));
        DraftObject composer;
        composer.setText(QStringLiteral("current in-memory value"));

        DraftPersistence persistence;
        QVERIFY(persistence.attach(&composer));
        QCOMPARE(composer.text(), QStringLiteral("current in-memory value"));

        persistence.flush();
        QCOMPARE(storedDraft(), QStringLiteral("current in-memory value"));
    }

    void rejectsObjectsWithoutWritableNotifiedTextProperty() {
        QObject object;
        DraftPersistence persistence;
        QVERIFY(!persistence.attach(&object));
    }
};

QTEST_GUILESS_MAIN(DraftPersistenceTest)
#include "draft-persistence-test.moc"
