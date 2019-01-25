app.controller('StatsController', ['$q', '$scope', '$http', '$interval', '$uibModal', 'AuthService', 'Restangular', '$window',
                              function ($q,   $scope,   $http,   $interval,   $uibModal,   AuthService,   Restangular, $window) {

        $scope.getIcons = function() {
            if (AuthService.getIcons()) {
                return AuthService.getIcons()[5];
            }
            else {
                return false;
            }
        };

        Restangular.setDefaultHeaders({token: AuthService.getToken()});

        $scope.currentView = "usageView";

        $scope.toggleClass = function(view){
            if ($scope.currentView == view){
                $scope.formView = view;
                return "active";
            }
            return undefined;
        }
        $scope.isCurrentView = function(view){
            if ($scope.currentView == view){
                return true;
            }
            return false;
        }

        $scope.dates = {
            "start": null,
            "end": null,
            "filter": null,
            "exclude": false,
            "stat": null
        };

        var exportStats = Restangular.all('export_stats/export_statistics');

        var stats = Restangular.oneUrl('stats');
        var inst = Restangular.oneUrl('export_stats/export_statistics');
        var monthlyInstances = Restangular.oneUrl('export_stats/export_statistics');
        var quartals = Restangular.oneUrl('export_stats/export_statistics');
        var quartalsByOrganization = Restangular.oneUrl('export_stats/export_statistics');
        
        stats.get().then(function (response) {
            $scope.stats = response;
        });    


        inst.get({'stat': 'institutions'}).then(function (response) {
            $scope.inst = response;
        });

        monthlyInstances.get({'stat': 'monthly_instances'}).then(function(response) {
            $scope.monthlyInstances = response;
        });

        quartals.get({'stat': 'quartals'}).then(function(response) {
            $scope.quartals = response;
        });
        
        quartalsByOrganization.get({'stat': 'quartals_by_org'}).then(function(response) {
            $scope.quartalsByOrganization = response;   
                 
        });

        $scope.downloadCSV = function(CSV, fileName) {
            var blob = new Blob([CSV], {type: 'text/csv'});
            var anchorLink = document.createElement('a');
            var mouseEvent = new MouseEvent('click');

            anchorLink.download = fileName + ".csv";
            anchorLink.href = window.URL.createObjectURL(blob);
            anchorLink.dataset.downloadurl = ['text/csv', anchorLink.download, anchorLink.href].join(',');
            anchorLink.dispatchEvent(mouseEvent);
        };

        $scope.getStatsCSV = function() {
            exportStats.getList($scope.dates).then(function(response) {
                var jsonStr = JSON.stringify(response);
                var jsonp = JSON.parse(jsonStr);
                jsonp = jsonp[0].data;
                var fileName = '';
                var CSV = '';
                var row = '';
                if ($scope.dates.stat === 'users') {
                    var headerString = 'User,Institution\r\n';
                    fileName = 'active_users'; 
                    CSV = headerString;
                    for (var d in jsonp) {
                        row = jsonp[d]['user'] + ',' + jsonp[d]['institution'] 
                        + '\r\n';
                        CSV += row;                   
                    };
                }
                else if ($scope.dates.stat === 'institutions') {
                    var headerString = 'Institution,Total users\r\n';
                    fileName = 'institutions';
                    CSV = headerString;
                    for (var d in jsonp) {
                        row = jsonp[d] + '\r\n';
                        CSV += row;                   
                    };
                }
                else if ($scope.dates.stat === 'monthly_instances') {
                    var headerString = 'Year,Jan,Feb,Mar,Apr,May,Jun,Jul,Aug,Sep,Oct,Nov,Dec,Total\r\n';
                    fileName = 'monthly_instances';
                    CSV = headerString;
                    for (var d in jsonp) {
                        row = d + ',' + jsonp[d] + '\r\n';
                        CSV += row;
                    };
                }
                else if ($scope.dates.stat === 'quartals' || $scope.dates.stat === 'quartals_by_org') {
                    if ($scope.dates.stat === 'quartals') { 
                        var headerString = 'User type,Year,Q1,Q2,Q3,Q4\r\n';
                        fileName = 'quartals';
                    };
                    if ($scope.dates.stat === 'quartals_by_org') { 
                        var headerString = 'Organization,Year,Q1,Q2,Q3,Q4\r\n'
                        fileName = 'quartals_by_organization';
                    };
                    CSV = headerString;
                    for (var d in jsonp) {
                        row = jsonp[d]['org'] + ',' + jsonp[d]['year'] + ','
                        + jsonp[d]['quartals'] + '\r\n';
                        CSV += row;
                    };

                }
                $scope.downloadCSV(CSV, fileName);
            }, function(response) {   
                if ('error' in response.data) {
                    error_message = response.data.error;
                    $.notify({title: 'HTTP ' + response.status, message: error_message}, {type: 'danger'});
                }
            });
        } 

        $scope.checkInput = function() {
            var validFilterInputRegex = /^([\w.-]+(?:,[\w.]+)*)$/gm;
            var dates = $scope.dates;
            if (dates === undefined) {
                return true;
            }
            var keys = Object.keys(dates);
            var filter = null;
            for (var key in keys) {
                if (keys[key] == 'filter') {
                    filter = dates['filter'];
                }
            }
            if (filter != null) {
                if (!validFilterInputRegex.test(filter)) {
                    return false;
                }
            }
            return true;
        };

        $scope.validForm = true;

        $scope.isValid = function() {
            if ($scope.validForm) {
                return true;
            }return false;
        };

        // Define which csv to download based on 
        // user selected view.
        $scope.downloader = function(date) {
            if (date != undefined) {
                if (date.start == null)
                   $scope.dates.start = date.start;
                else
                   $scope.dates.start = date.start.toLocaleDateString();
                if (date.end == null)
                   $scope.dates.end = date.end;
                else
                   $scope.dates.end = date.end.toLocaleDateString();
                $scope.dates.filter = date.filter;
                $scope.dates.exclude = date.exclude;
            };
            for (item in $scope.dates) {
                if ($scope.dates[item] === undefined || $scope.dates[item] === '') {
                    $scope.dates[item] = null;
                }
            };
            var valid = $scope.checkInput();
            if (!valid) {
                $scope.validForm = false;
            }else {
                $scope.validForm = true;
                var view = $scope.formView;

                if (view == 'usageView') {
                    return;
                }else if (view == 'userView'){
                    $scope.dates.stat = 'users';
                }else if (view == 'institutionView') {
                    $scope.dates.stat = 'institutions';
                }else if (view == 'quartalView') {
                    $scope.dates.stat = 'quartals';
                }else if (view == 'organizationQuartalView') {
                    $scope.dates.stat = 'quartals_by_org';
                }else if (view == 'monthlyView') {
                    $scope.dates.stat = 'monthly_instances';
                }
                $scope.getStatsCSV();
            }       
        };

}]);
