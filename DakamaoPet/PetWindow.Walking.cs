// SPDX-License-Identifier: CC-BY-NC-SA-4.0
// 本项目有权许可的新增贡献适用；上游鸣潮/大卡猫形象的 CC 授权未确认。
// 第三方组件保留原许可，范围及公益声明见《项目开发文档》。
using System;
using System.Diagnostics;
using System.Linq;
using System.Windows.Threading;
using static VPet_Simulator.Core.GraphInfo;

namespace DakamaoPet;

public partial class PetWindow
{
    private bool _walking;
    private bool _walkStopping;
    private bool _walkMoving;
    private int _walkDirection;
    private int _walkGeneration;
    private int _walkBlinkCounter;
    private double _walkDestination;
    private DispatcherTimer? _walkTimer;
    private readonly Stopwatch _walkClock = new();

    private void StartWalk()
    {
        if (_main == null || !_petReady) return;
        StopPreview(false);
        CancelSleep(false);
        CancelFall();
        _walking = true;
        _walkStopping = false;
        _walkBlinkCounter = 0;
        _walkGeneration++;
        _main.EventTimer.Stop();
        Top = GetDesktopWorkArea().Bottom - ActualHeight;
        _walkTimer ??= new DispatcherTimer(DispatcherPriority.Render)
        {
            Interval = TimeSpan.FromMilliseconds(16)
        };
        _walkTimer.Tick -= WalkTimer_Tick;
        _walkTimer.Tick += WalkTimer_Tick;
        _walkClock.Restart();
        _walkTimer.Start();
        BeginWalkLeg();
    }

    private void BeginWalkLeg()
    {
        var desktop = GetDesktopWorkArea();
        var min = desktop.Left;
        var max = Math.Max(min, desktop.Right - ActualWidth);
        Left = Math.Clamp(Left, min, max);
        var leftRoom = Left - min;
        var rightRoom = max - Left;
        _walkDirection = _walkDirection == 0
            ? (leftRoom > rightRoom ? -1 : 1)
            : -_walkDirection;
        if (leftRoom < 80) _walkDirection = 1;
        if (rightRoom < 80) _walkDirection = -1;
        SetWalkDestination();
        App.WriteLog($"WALK direction={_walkDirection} from={Left:F1} to={_walkDestination:F1} floor={Top:F1}");
        DisplayWalkStage(AnimatType.A_Start, () =>
        {
            _walkMoving = !_walkStopping;
            _walkClock.Restart();
            PlayWalkSteps();
        });
    }

    private void PlayWalkSteps()
    {
        DisplayWalkStage(AnimatType.B_Loop, () =>
        {
            _walkBlinkCounter++;
            if (!_walkStopping && _walkBlinkCounter % 4 == 0)
                DisplayWalkStage(AnimatType.Single, AfterWalkStep,
                    _walkDirection < 0 ? "walk_left_blink" : "walk_right_blink");
            else
                AfterWalkStep();
        });
    }

    private void AfterWalkStep()
    {
            if (!_walkStopping && (Math.Abs(Left - _walkDestination) > 0.5 || ContinueWalkForward()))
            {
                PlayWalkSteps();
                return;
            }
            _walkMoving = false;
            DisplayWalkStage(AnimatType.C_End, () =>
            {
                if (_walkStopping)
                {
                    _walking = false;
                    _walkTimer?.Stop();
                    _walkClock.Stop();
                    App.WriteLog($"WALK stopped left={Left:F1} top={Top:F1}");
                    FinishAction();
                }
                else
                    BeginWalkLeg();
            });
    }

    private void SetWalkDestination()
    {
        var desktop = GetDesktopWorkArea();
        _walkDestination = Math.Clamp(Left + _walkDirection * Random.Shared.Next(420, 781) * _petScale,
            desktop.Left, Math.Max(desktop.Left, desktop.Right - ActualWidth));
    }

    private bool ContinueWalkForward()
    {
        var desktop = GetDesktopWorkArea();
        var room = _walkDirection < 0 ? Left - desktop.Left : desktop.Right - ActualWidth - Left;
        if (room < 80 * _petScale) return false;
        SetWalkDestination();
        _walkMoving = true;
        App.WriteLog($"WALK continue direction={_walkDirection} from={Left:F1} to={_walkDestination:F1}");
        return true;
    }

    private void DisplayWalkStage(AnimatType stage, Action after, string? overrideName = null)
    {
        var generation = _walkGeneration;
        var name = overrideName ?? (_walkDirection < 0 ? "walk_left" : "walk_right");
        var animation = _previewActions[name].First(item => item.GraphInfo.Animat == stage);
        DisplayAnimation(animation, () => Dispatcher.BeginInvoke(() =>
        {
            if (_walking && generation == _walkGeneration) after();
        }, DispatcherPriority.Render));
    }

    private void WalkTimer_Tick(object? sender, EventArgs e)
    {
        var elapsed = Math.Min(_walkClock.Elapsed.TotalSeconds, 0.05);
        _walkClock.Restart();
        if (!_walkMoving || ActionRing.IsOpen || SizePopup.IsOpen || _settingsPage!=null || _declarationPage!=null) return;
        var desktop = GetDesktopWorkArea();
        _walkDestination = Math.Clamp(_walkDestination, desktop.Left, Math.Max(desktop.Left, desktop.Right - ActualWidth));
        var delta = _walkDestination - Left;
        Left += Math.Sign(delta) * Math.Min(Math.Abs(delta), 32 * _petScale * elapsed);
        Top = desktop.Bottom - ActualHeight;
        if (Math.Abs(Left - _walkDestination) < 0.5) _walkMoving = false;
    }

    private void StopWalk(Action? after = null)
    {
        if (!_walking)
        {
            after?.Invoke();
            return;
        }
        _walkStopping = true;
        _walkMoving = false;
        _pendingAction = after;
        App.WriteLog("WALK settle_requested");
    }

    private void CancelWalk()
    {
        _walking = false;
        _walkMoving = false;
        _walkStopping = false;
        _walkGeneration++;
        _walkTimer?.Stop();
        _walkClock.Stop();
    }
}
