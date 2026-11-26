package cn.gaoming.tv;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInstaller;

public final class UpdateInstallReceiver extends BroadcastReceiver {
    static final String ACTION = "cn.gaoming.tv.UPDATE_INSTALL_RESULT";

    @Override
    public void onReceive(Context context, Intent intent) {
        if (!ACTION.equals(intent.getAction())) {
            return;
        }
        int status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
        if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            GitHubUpdate.confirmInstall(context, intent.getParcelableExtra(Intent.EXTRA_INTENT));
            return;
        }
        String message;
        switch (status) {
            case PackageInstaller.STATUS_SUCCESS:
                message = "更新已安装";
                break;
            case PackageInstaller.STATUS_FAILURE_ABORTED:
                message = "已取消安装";
                break;
            case PackageInstaller.STATUS_FAILURE_BLOCKED:
                message = "系统阻止了本次安装，请检查安装应用权限";
                break;
            case PackageInstaller.STATUS_FAILURE_STORAGE:
                message = "存储空间不足，无法安装更新";
                break;
            default:
                message = "系统无法安装更新（状态 " + status + "）";
        }
        GitHubUpdate.finish(context, message);
    }
}
