#!/usr/local/CyberCP/bin/python
import os.path
import sys
import django
from plogical.httpProc import httpProc
sys.path.append('/usr/local/CyberCP')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "CyberCP.settings")
django.setup()
from django.shortcuts import redirect
from django.http import HttpResponse
from loginSystem.views import loadLoginPage
from loginSystem.models import Administrator
import json
from .models import Package
from plogical.acl import ACLManager
from plogical.processUtilities import ProcessUtilities

class PackagesManager:
    def __init__(self, request = None):
        self.request  = request

    @staticmethod
    def checkAddonAccess():
        """
        Softi: resource limits are always available (no CyberPanel addons paywall).
        Limits are configured per Package in the panel and enforced by Softi
        (systemd user slice + OLS vhost fields). Upstream used a remote addon check.
        """
        return True

    def packagesHome(self):
        proc = httpProc(self.request, 'packages/index.html',
                        None, 'createPackage')
        return proc.render()

    def createPacakge(self):
        userID = self.request.session['userID']
        admin = Administrator.objects.get(pk=userID)
        has_addons = self.checkAddonAccess()
        proc = httpProc(self.request, 'packages/createPackage.html',
                        {"adminNamePackage": admin.userName, "has_addons": has_addons}, 'createPackage')
        return proc.render()

    def deletePacakge(self):
        userID = self.request.session['userID']
        currentACL = ACLManager.loadedACL(userID)
        packageList = ACLManager.loadPackages(userID, currentACL)
        proc = httpProc(self.request, 'packages/deletePackage.html',
                        {"packageList": packageList}, 'deletePackage')
        return proc.render()

    def submitPackage(self):
        try:

            userID = self.request.session['userID']
            currentACL = ACLManager.loadedACL(userID)

            if ACLManager.currentContextPermission(currentACL, 'createPackage') == 0:
                return ACLManager.loadErrorJson('saveStatus', 0)

            data = json.loads(self.request.body)
            packageName = data['packageName'].replace(' ', '')
            packageSpace = int(data['diskSpace'])
            packageBandwidth = int(data['bandwidth'])
            packageDatabases = int(data['dataBases'])
            ftpAccounts = int(data['ftpAccounts'])
            emails = int(data['emails'])
            allowedDomains = int(data['allowedDomains'])

            try:
                api = data['api']
            except:
                api = '0'

            try:
                allowFullDomain = int(data['allowFullDomain'])
            except:
                allowFullDomain = 1

            try:
                enforceDiskLimits = int(data['enforceDiskLimits'])
            except:
                enforceDiskLimits = 0

            # Resource Limits - with backward compatibility
            try:
                memoryLimitMB = int(data['memoryLimitMB'])
            except:
                memoryLimitMB = 1024

            try:
                cpuCores = int(data['cpuCores'])
            except:
                cpuCores = 1

            try:
                ioLimitMBPS = int(data['ioLimitMBPS'])
            except:
                ioLimitMBPS = 10

            try:
                inodeLimit = int(data['inodeLimit'])
            except:
                inodeLimit = 400000

            try:
                maxConnections = int(data['maxConnections'])
            except:
                maxConnections = 10

            try:
                procSoftLimit = int(data['procSoftLimit'])
            except:
                procSoftLimit = 400

            try:
                procHardLimit = int(data['procHardLimit'])
            except:
                procHardLimit = 500

            if packageSpace < 0 or packageBandwidth < 0 or packageDatabases < 0 or ftpAccounts < 0 or emails < 0 or allowedDomains < 0:
                data_ret = {'saveStatus': 0, 'error_message': "All values should be positive or 0."}
                json_data = json.dumps(data_ret)
                return HttpResponse(json_data)

            # Check addon access for resource limits feature
            has_addons = self.checkAddonAccess()
            if not has_addons and enforceDiskLimits == 1:
                data_ret = {'saveStatus': 0, 'error_message': "Resource limits feature requires CyberPanel addons. Please visit https://cyberpanel.net/cyberpanel-addons to purchase."}
                json_data = json.dumps(data_ret)
                return HttpResponse(json_data)

            # Reset resource limits to defaults if addons not available
            if not has_addons:
                enforceDiskLimits = 0
                memoryLimitMB = 1024
                cpuCores = 1
                ioLimitMBPS = 10
                inodeLimit = 400000
                maxConnections = 10
                procSoftLimit = 400
                procHardLimit = 500

            # Validate resource limits
            if memoryLimitMB < 256 or cpuCores < 1 or ioLimitMBPS < 1 or inodeLimit < 10000 or maxConnections < 1 or procSoftLimit < 1 or procHardLimit < 1:
                data_ret = {'saveStatus': 0, 'error_message': "Resource limits must be positive and within valid ranges."}
                json_data = json.dumps(data_ret)
                return HttpResponse(json_data)

            admin = Administrator.objects.get(pk=userID)

            if api == '0':
                packageName = admin.userName + "_" + packageName

            package = Package(admin=admin, packageName=packageName, diskSpace=packageSpace,
                              bandwidth=packageBandwidth, ftpAccounts=ftpAccounts, dataBases=packageDatabases,
                              emailAccounts=emails, allowedDomains=allowedDomains, allowFullDomain=allowFullDomain,
                              enforceDiskLimits=enforceDiskLimits, memoryLimitMB=memoryLimitMB, cpuCores=cpuCores,
                              ioLimitMBPS=ioLimitMBPS, inodeLimit=inodeLimit, maxConnections=maxConnections,
                              procSoftLimit=procSoftLimit, procHardLimit=procHardLimit)

            package.save()

            # Softi: apply Package limits to any existing sites on this package
            try:
                from plogical.softiPackageEnforce import apply_package_to_all_websites
                apply_package_to_all_websites(package)
            except Exception as softi_err:
                logging_msg = f"SOFTI package enforce after create: {softi_err}"
                try:
                    from plogical.CyberCPLogFileWriter import CyberCPLogFileWriter as logging
                    logging.writeToFile(logging_msg)
                except Exception:
                    pass

            data_ret = {'status': 1, 'saveStatus': 1, 'error_message': "None"}
            json_data = json.dumps(data_ret)
            return HttpResponse(json_data)

        except BaseException as msg:
            data_ret = {'status': 0, 'saveStatus': 0, 'error_message': str(msg)}
            json_data = json.dumps(data_ret)
            return HttpResponse(json_data)

    def submitDelete(self):
        try:
            userID = self.request.session['userID']
            currentACL = ACLManager.loadedACL(userID)

            if ACLManager.currentContextPermission(currentACL, 'deletePackage') == 0:
                return ACLManager.loadErrorJson('deleteStatus', 0)

            data = json.loads(self.request.body)
            packageName = data['packageName']

            delPackage = Package.objects.get(packageName=packageName)

            ## Check package ownership
            admin = Administrator.objects.get(pk=userID)
            if ACLManager.CheckPackageOwnership(delPackage, admin, currentACL) == 0:
                return ACLManager.loadErrorJson('deleteStatus', 0)

            delPackage.delete()

            data_ret = {'status': 1, 'deleteStatus': 1, 'error_message': "None"}
            json_data = json.dumps(data_ret)
            return HttpResponse(json_data)


        except BaseException as msg:
            data_ret = {'status': 0, 'deleteStatus': 0, 'error_message': str(msg)}
            json_data = json.dumps(data_ret)
            return HttpResponse(json_data)

    def modifyPackage(self):
        userID = self.request.session['userID']
        currentACL = ACLManager.loadedACL(userID)
        packageList = ACLManager.loadPackages(userID, currentACL)
        has_addons = self.checkAddonAccess()
        proc = httpProc(self.request, 'packages/modifyPackage.html',
                        {"packList": packageList, "has_addons": has_addons}, 'modifyPackage')
        return proc.render()

    def submitModify(self):
        try:
            userID = self.request.session['userID']
            data = json.loads(self.request.body)
            packageName = data['packageName']

            currentACL = ACLManager.loadedACL(userID)

            if ACLManager.currentContextPermission(currentACL, 'modifyPackage') == 0:
                return ACLManager.loadErrorJson('modifyStatus', 0)

            modifyPack = Package.objects.get(packageName=packageName)

            ## Check package ownership
            admin = Administrator.objects.get(pk=userID)
            if ACLManager.CheckPackageOwnership(modifyPack, admin, currentACL) == 0:
                return ACLManager.loadErrorJson('deleteStatus', 0)

            diskSpace = modifyPack.diskSpace
            bandwidth = modifyPack.bandwidth
            ftpAccounts = modifyPack.ftpAccounts
            dataBases = modifyPack.dataBases
            emails = modifyPack.emailAccounts


            data_ret = {'emails': emails, 'modifyStatus': 1, 'error_message': "None",
                        "diskSpace": diskSpace, "bandwidth": bandwidth, "ftpAccounts": ftpAccounts,
                        "dataBases": dataBases, "allowedDomains": modifyPack.allowedDomains,
                        'allowFullDomain': modifyPack.allowFullDomain, 'enforceDiskLimits': modifyPack.enforceDiskLimits,
                        'memoryLimitMB': modifyPack.memoryLimitMB, 'cpuCores': modifyPack.cpuCores,
                        'ioLimitMBPS': modifyPack.ioLimitMBPS, 'inodeLimit': modifyPack.inodeLimit,
                        'maxConnections': modifyPack.maxConnections, 'procSoftLimit': modifyPack.procSoftLimit,
                        'procHardLimit': modifyPack.procHardLimit}
            json_data = json.dumps(data_ret)
            return HttpResponse(json_data)

        except BaseException as msg:
            data_ret = {'modifyStatus': 0, 'error_message': str(msg)}
            json_data = json.dumps(data_ret)
            return HttpResponse(json_data)

    def saveChanges(self):
        try:

            userID = self.request.session['userID']
            currentACL = ACLManager.loadedACL(userID)

            admin = Administrator.objects.get(pk=userID)

            if ACLManager.currentContextPermission(currentACL, 'modifyPackage') == 0:
                return ACLManager.loadErrorJson('saveStatus', 0)

            data = json.loads(self.request.body)
            packageName = data['packageName']

            if data['diskSpace'] < 0 or data['bandwidth'] < 0 or data['ftpAccounts'] < 0 or data[
                'dataBases'] < 0 or \
                            data['emails'] < 0 or data['allowedDomains'] < 0:
                data_ret = {'saveStatus': 0, 'error_message': "All values should be positive or 0."}
                json_data = json.dumps(data_ret)
                return HttpResponse(json_data)

            modifyPack = Package.objects.get(packageName=packageName)

            if modifyPack.admin == admin:

                modifyPack.diskSpace = data['diskSpace']
                modifyPack.bandwidth = data['bandwidth']
                modifyPack.ftpAccounts = data['ftpAccounts']
                modifyPack.dataBases = data['dataBases']
                modifyPack.emailAccounts = data['emails']
                modifyPack.allowedDomains = data['allowedDomains']

                try:
                    modifyPack.allowFullDomain = int(data['allowFullDomain'])
                except:
                    modifyPack.allowFullDomain = 1

                try:
                    modifyPack.enforceDiskLimits = int(data['enforceDiskLimits'])
                except:
                    modifyPack.enforceDiskLimits = 0

                # Check addon access for resource limits feature
                has_addons = self.checkAddonAccess()
                if not has_addons and modifyPack.enforceDiskLimits == 1:
                    data_ret = {'saveStatus': 0, 'error_message': "Resource limits feature requires CyberPanel addons. Please visit https://cyberpanel.net/cyberpanel-addons to purchase."}
                    json_data = json.dumps(data_ret)
                    return HttpResponse(json_data)

                # Reset resource limits to defaults if addons not available
                if not has_addons:
                    modifyPack.enforceDiskLimits = 0
                    modifyPack.memoryLimitMB = 1024
                    modifyPack.cpuCores = 1
                    modifyPack.ioLimitMBPS = 10
                    modifyPack.inodeLimit = 400000
                    modifyPack.maxConnections = 10
                    modifyPack.procSoftLimit = 400
                    modifyPack.procHardLimit = 500

                # Update resource limits (only if addons available)
                if has_addons:
                    try:
                        modifyPack.memoryLimitMB = int(data['memoryLimitMB'])
                    except:
                        pass  # Keep existing value

                    try:
                        modifyPack.cpuCores = int(data['cpuCores'])
                    except:
                        pass  # Keep existing value

                    try:
                        modifyPack.ioLimitMBPS = int(data['ioLimitMBPS'])
                    except:
                        pass  # Keep existing value

                    try:
                        modifyPack.inodeLimit = int(data['inodeLimit'])
                    except:
                        pass  # Keep existing value

                    try:
                        modifyPack.maxConnections = int(data['maxConnections'])
                    except:
                        pass  # Keep existing value

                    try:
                        modifyPack.procSoftLimit = int(data['procSoftLimit'])
                    except:
                        pass  # Keep existing value

                    try:
                        modifyPack.procHardLimit = int(data['procHardLimit'])
                    except:
                        pass  # Keep existing value

                modifyPack.save()

                # Softi: re-apply Package limits to all websites using this package
                try:
                    from plogical.softiPackageEnforce import apply_package_to_all_websites
                    apply_package_to_all_websites(modifyPack)
                except Exception as softi_err:
                    try:
                        from plogical.CyberCPLogFileWriter import CyberCPLogFileWriter as logging
                        logging.writeToFile(f"SOFTI package enforce after modify: {softi_err}")
                    except Exception:
                        pass

                ## Fix https://github.com/usmannasir/cyberpanel/issues/998

                # from plogical.IncScheduler import IncScheduler
                # isPU = IncScheduler('CalculateAndUpdateDiskUsage', {})
                # isPU.start()

                from plogical.processUtilities import ProcessUtilities
                command = '/usr/local/CyberCP/bin/python /usr/local/CyberCP/plogical/IncScheduler.py UpdateDiskUsageForce'
                ProcessUtilities.outputExecutioner(command)

                data_ret = {'status': 1, 'saveStatus': 1, 'error_message': "None"}
                json_data = json.dumps(data_ret)
                return HttpResponse(json_data)
            else:
                data_ret = {'status': 0, 'saveStatus': 0, 'error_message': "You don't own this package."}
                json_data = json.dumps(data_ret)
                return HttpResponse(json_data)

        except BaseException as msg:
            data_ret = {'status': 0, 'saveStatus': 0, 'error_message': str(msg)}
            json_data = json.dumps(data_ret)
            return HttpResponse(json_data)


    def listPackages(self):
        userID = self.request.session['userID']
        currentACL = ACLManager.loadedACL(userID)
        packageList = ACLManager.loadPackages(userID, currentACL)
        proc = httpProc(self.request, 'packages/listPackages.html',
                        {"packList": packageList}, 'listPackages')
        return proc.render()

    def listPackagesAPI(self,data=None):
        """
            List of packages for API
        :param data:
        :return HttpResponse:
        """
        try:
            adminUser = data['adminUser']
            admin = Administrator.objects.get(userName=adminUser)
            currentACL = ACLManager.loadedACL(admin.id)
            packageList = ACLManager.loadPackages(admin.id, currentACL)
            return HttpResponse(json.dumps(packageList))
        except BaseException as msg:
            data_ret = {'status': 0, 'error_message': str(msg)}
            json_data = json.dumps(data_ret)
            return HttpResponse(json_data)

    def fetchPackagesTable(self):
        try:
            userID = self.request.session['userID']

            currentACL = ACLManager.loadedACL(userID)

            if ACLManager.currentContextPermission(currentACL, 'listPackages') == 0:
                return ACLManager.loadErrorJson()


            packages = ACLManager.loadPackageObjects(userID, currentACL)

            json_data = "["
            checker = 0

            for items in packages:

                dic = {'package': items.packageName,
                       'diskSpace': items.diskSpace,
                       'bandwidth': items.bandwidth,
                       'emailAccounts': items.emailAccounts,
                       'dataBases': items.dataBases,
                       'ftpAccounts': items.ftpAccounts,
                       'allowedDomains': items.allowedDomains,
                       'allowFullDomain': items.allowFullDomain,
                       'enforceDiskLimits': items.enforceDiskLimits
                       }

                if checker == 0:
                    json_data = json_data + json.dumps(dic)
                    checker = 1
                else:
                    json_data = json_data + ',' + json.dumps(dic)

            json_data = json_data + ']'

            final_json = json.dumps({'status': 1, 'fetchStatus': 1, 'error_message': "None", "data": json_data})
            return HttpResponse(final_json)

        except KeyError:
            return redirect(loadLoginPage)

    # ── Softi: plan usage per website / account ──────────────────────────

    def planUsage(self):
        """Admin page: plan Softi asignado + uso disco/RAM/CPU."""
        proc = httpProc(self.request, 'packages/planUsage.html', {"status": 1}, 'admin')
        return proc.render()

    def fetchPlanUsage(self):
        """
        Softi JSON: Package limits + disk (FindStats) + live RAM/CPU approx (ps).
        Filters (POST JSON): packageFilter, ownerFilter, stateFilter, q
        """
        try:
            from plogical.virtualHostUtilities import virtualHostUtilities
            from plogical.softiPackageEnforce import (
                softi_cpu_quota_percent,
                softi_memory_max,
                snapshot_process_usage_by_home,
            )

            userID = self.request.session['userID']
            currentACL = ACLManager.loadedACL(userID)
            if currentACL.get('admin') != 1:
                return ACLManager.loadErrorJson()

            data = {}
            if self.request.method == 'GET':
                data = {
                    'packageFilter': self.request.GET.get('packageFilter', ''),
                    'ownerFilter': self.request.GET.get('ownerFilter', ''),
                    'stateFilter': self.request.GET.get('stateFilter', ''),
                    'q': self.request.GET.get('q', '') or self.request.GET.get('search', ''),
                }
            else:
                raw = self.request.body or b'{}'
                try:
                    data = json.loads(
                        raw.decode('utf-8') if isinstance(raw, (bytes, bytearray)) else raw
                    )
                except Exception:
                    data = {}

            package_filter = (data.get('packageFilter') or '').strip()
            owner_filter = (data.get('ownerFilter') or '').strip()
            state_filter = (data.get('stateFilter') or '').strip().lower()
            q = (data.get('q') or data.get('search') or '').strip().lower()

            websites = list(ACLManager.findWebsiteObjects(currentACL, userID))
            packages = sorted({
                w.package.packageName for w in websites if getattr(w, 'package', None)
            })
            owners = sorted({
                w.admin.userName for w in websites if getattr(w, 'admin', None)
            })

            if package_filter and package_filter not in ('', '*', 'all'):
                websites = [
                    w for w in websites
                    if getattr(w, 'package', None)
                    and w.package.packageName == package_filter
                ]
            if owner_filter and owner_filter not in ('', '*', 'all'):
                websites = [
                    w for w in websites
                    if getattr(w, 'admin', None) and w.admin.userName == owner_filter
                ]
            if state_filter in ('active', '1'):
                websites = [w for w in websites if w.state == 1]
            elif state_filter in ('suspended', '0'):
                websites = [w for w in websites if w.state != 1]
            if q:
                websites = [
                    w for w in websites
                    if q in (w.domain or '').lower()
                    or q in (getattr(w, 'externalApp', '') or '').lower()
                    or q in (getattr(w, 'adminEmail', '') or '').lower()
                ]

            homes = {}
            for w in websites:
                user = (w.externalApp or '').strip()
                if user:
                    homes[user] = f"/home/{w.domain}"
            live = snapshot_process_usage_by_home(homes)

            rows = []
            for website in websites:
                pkg = website.package
                disk_quota_mb = int(getattr(pkg, 'diskSpace', 0) or 0)
                mem_mb = int(getattr(pkg, 'memoryLimitMB', 0) or 0)
                cpu_cores = int(getattr(pkg, 'cpuCores', 1) or 1)
                try:
                    disk_used_mb, disk_pct, _bw, _bw_pct = virtualHostUtilities.FindStats(website)
                except Exception:
                    disk_used_mb, disk_pct = 0, 0
                try:
                    disk_used_mb = int(float(disk_used_mb or 0))
                except Exception:
                    disk_used_mb = 0
                try:
                    disk_pct = int(float(disk_pct or 0))
                except Exception:
                    disk_pct = 0
                if disk_quota_mb > 0 and disk_pct <= 0:
                    disk_pct = min(100, int(round(100.0 * disk_used_mb / disk_quota_mb)))

                home = f"/home/{website.domain}"
                snap = live.get(home) or {}
                mem_used = int(snap.get('memoryUsedMB') or 0)
                cpu_used = float(snap.get('cpuPct') or 0)
                mem_used_pct = 0
                if mem_mb > 0:
                    mem_used_pct = min(999, int(round(100.0 * mem_used / mem_mb)))

                pkg_name = pkg.packageName if pkg else ''
                short = pkg_name[6:] if pkg_name.startswith('admin_') else pkg_name
                state = 'Active' if website.state == 1 else 'Suspended'
                rows.append({
                    'domain': website.domain,
                    'admin': website.admin.userName if website.admin_id else '',
                    'adminEmail': website.adminEmail or '',
                    'externalApp': website.externalApp or '',
                    'package': pkg_name,
                    'packageShort': short,
                    'state': state,
                    'diskUsedMB': disk_used_mb,
                    'diskQuotaMB': disk_quota_mb,
                    'diskUsedPct': disk_pct,
                    'memoryLimitMB': mem_mb,
                    'memoryMax': softi_memory_max(pkg) if pkg else '',
                    'memoryUsedMB': mem_used,
                    'memoryUsedPct': mem_used_pct,
                    'cpuCores': cpu_cores,
                    'cpuQuotaPct': softi_cpu_quota_percent(pkg) if pkg else 0,
                    'cpuUsedPct': cpu_used,
                    'procCount': int(snap.get('procCount') or 0),
                    'usageNote': snap.get('note') or '',
                    'enforceDiskLimits': int(getattr(pkg, 'enforceDiskLimits', 0) or 0),
                    'procHardLimit': int(getattr(pkg, 'procHardLimit', 0) or 0),
                })

            rows.sort(key=lambda r: (-r['memoryUsedMB'], -r['diskUsedPct'], r['domain']))

            summary = {
                'total': len(rows),
                'active': sum(1 for r in rows if r['state'] == 'Active'),
                'suspended': sum(1 for r in rows if r['state'] != 'Active'),
                'byPackage': {},
                'memoryLiveNote': (
                    'RAM/CPU live: ps + cwd + PM2 + Docker. '
                    'Sitios PHP sin lsphp activo aparecen en 0 (idle). '
                    'OLS shared (nobody) no se reparte por dominio.'
                ),
            }
            for r in rows:
                key = r['packageShort'] or r['package'] or '(none)'
                summary['byPackage'][key] = summary['byPackage'].get(key, 0) + 1

            return HttpResponse(json.dumps({
                'status': 1,
                'rows': rows,
                'packages': packages,
                'owners': owners,
                'summary': summary,
            }), content_type='application/json')

        except BaseException as msg:
            return HttpResponse(json.dumps({
                'status': 0,
                'error_message': str(msg),
            }), content_type='application/json')
